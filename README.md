# Odoo 18 Multi-Delivery

## Bài toán

Một khách hàng đặt một đơn bán hàng (`sale.order`) nhưng muốn nhận hàng ở nhiều địa điểm khác nhau. Yêu cầu: một đơn tạo ra nhiều phiếu kho (`stock.picking`), mỗi phiếu giao đến một địa chỉ do người dùng chọn.

## Hướng giải quyết

Giữ nguyên toàn bộ luồng chuẩn của Odoo (Sales → Inventory → Invoicing), không viết lại việc tạo phiếu kho. Mỗi dòng đơn hàng được gắn thêm một địa chỉ nhận. Khi xác nhận đơn, các dòng được chia thành các nhóm cung ứng riêng theo địa chỉ, và Odoo tự tạo một phiếu kho cho mỗi nhóm.

Cùng một sản phẩm có thể xuất hiện trên nhiều dòng, mỗi dòng một số lượng và một địa chỉ:

| Dòng | Sản phẩm | Số lượng | Địa chỉ nhận |
|---|---|---:|---|
| 1 | Laptop | 4 | Văn phòng A |
| 2 | Laptop | 3 | Văn phòng B |
| 3 | Laptop | 3 | Văn phòng C |

Xác nhận đơn cho ra 3 phiếu giao, mỗi phiếu đúng người nhận và đúng số lượng.

## Kiến trúc

Hệ thống gồm 3 tầng, chỉ tầng trên cùng là code của dự án này:

```text
┌─────────────────────────────────────────────────────────────┐
│ sale_multi_delivery            (repo này, code tự viết)     │
│   - Địa chỉ phải thuộc khách hàng của đơn                   │
│   - Không đổi địa chỉ của dòng sau khi đơn đã xác nhận      │
├─────────────────────────────────────────────────────────────┤
│ OCA sale-workflow 18.0         (addon cộng đồng, không sửa) │
│   - sale_stock_delivery_address                             │
│   - sale_procurement_group_by_line                          │
├─────────────────────────────────────────────────────────────┤
│ Odoo 18 core                   (không sửa)                  │
│   sale → sale_stock → stock  (+ account cho hóa đơn)        │
└─────────────────────────────────────────────────────────────┘
```

| Tầng | Vai trò | Nguồn |
|---|---|---|
| Odoo core | Đơn bán, cung ứng, phiếu kho, giữ hàng, backorder, hóa đơn | `odoo/odoo` nhánh 18.0 |
| OCA | Thêm địa chỉ nhận trên từng dòng và tách nhóm cung ứng theo địa chỉ | `OCA/sale-workflow` nhánh 18.0, commit `e0694c7bd12d1d286b2a8ebe8e8f0130d1290942` |
| `sale_multi_delivery` | Bổ sung hai quy tắc nghiệp vụ mà OCA chưa có | Repo này |

### Luồng xử lý khi xác nhận đơn

```text
sale.order.action_confirm()
  → _action_confirm()                       (hook của sale_stock)
  → sale.order.line._action_launch_stock_rule()
      → _get_procurement_group_key()        mỗi dòng một khóa nhóm
          mặc định        (8,  order.id)    mọi dòng chung một nhóm
          có dest_address (15, địa chỉ)     mỗi địa chỉ một nhóm
  → procurement.group.run()                 đặt partner và địa điểm đích theo địa chỉ
  → stock.rule → stock.move
  → stock.move._assign_picking()            gom move theo (group, địa điểm, loại phiếu)
  → stock.picking                           mỗi nhóm một phiếu giao
```

Điểm mấu chốt: khi gom move vào phiếu, Odoo so sánh `procurement.group` của move; `partner_id` chỉ được xét khi move không thuộc nhóm nào. Move sinh từ đơn bán luôn có nhóm, nên để tách phiếu theo địa chỉ thì phải tách nhóm cung ứng, và đó chính là việc OCA làm.

Sau khi tạo phiếu, mọi thứ tiếp theo là cơ chế chuẩn: mỗi phiếu được giữ hàng và xác nhận độc lập, số lượng đã giao được cập nhật theo từng dòng đơn, hóa đơn lập từ đơn gốc và bám theo số lượng đã giao (với sản phẩm theo chính sách "Delivered quantities").

### Mô hình dữ liệu

Không có model mới. Chỉ mở rộng model có sẵn:

| Model | Field | Nguồn | Ý nghĩa |
|---|---|---|---|
| `sale.order.line` | `dest_address_id` (Many2one `res.partner`) | OCA | Địa chỉ nhận của dòng; để trống thì dùng địa chỉ giao ở đầu đơn |
| `sale.order.line` | `procurement_group_id` | OCA | Nhóm cung ứng mà dòng thuộc về |
| `sale.order` | `delivery_commercial_partner_id` (related, không lưu) | Repo này | Công ty gốc của khách hàng, để view lọc danh sách địa chỉ |

Liên kết giữa các model chuẩn: `stock.move.sale_line_id` → `sale.order.line`; `stock.picking.sale_id` được tính từ `group_id.sale_id`, nên nút Delivery trên đơn bán thấy đủ các phiếu.

### Phần code của dự án

`custom_addons/sale_multi_delivery` chỉ có hai quy tắc, đều dùng cơ chế mở rộng chuẩn của Odoo (`_inherit`, `@api.constrains`, override `write`, view kế thừa):

1. **Địa chỉ hợp lệ.** Địa chỉ của dòng phải thuộc khách hàng của đơn và không phải loại hóa đơn hoặc riêng tư. Giao diện lọc danh sách chọn; server kiểm tra lại bằng `@api.constrains` (cũng chạy lại khi đổi khách hàng), để chặn cả import và RPC.
2. **Khóa địa chỉ sau xác nhận.** Khi đơn đã ở trạng thái Sale Order, không đổi được địa chỉ của dòng đã có. Giao diện đặt chỉ-đọc; server chặn trong `write()`.

Dự án cố ý không override `action_confirm`, `_action_launch_stock_rule`, `_assign_picking` hay `button_validate`, để không phải bảo trì lại phần lõi của Odoo.

## Phạm vi và giới hạn

- Một công ty, một kho, xuất kho một bước. Chưa hỗ trợ kho nhiều bước, nhiều kho, dropship hay MTO.
- Phân hệ Mua hàng không bị chạm tới; chuỗi Sales → Purchase đã được nghiên cứu trong source nhưng không thuộc phạm vi tính năng này.
- Dòng để trống địa chỉ dùng địa chỉ giao ở đầu đơn và thuộc một nhóm riêng, nên có thể ra một phiếu riêng dù trùng địa chỉ với dòng khác.
- Vẫn thêm được dòng mới có địa chỉ sau khi xác nhận; chỉ việc đổi địa chỉ của dòng cũ bị chặn.
- Addon OCA `sale_procurement_group_by_line` chép lại thân hàm `_action_launch_stock_rule` của core thay vì bọc bằng `super()`. Vì vậy phải ghim commit OCA và kiểm tra lại khi nâng cấp Odoo.
- Giấy phép OCA là AGPL-3; addon của repo này là LGPL-3.

## Cấu trúc thư mục

```text
custom_addons/sale_multi_delivery/   addon (manifest, models, views, tests, README hướng dẫn demo)
oca/sale-workflow/                   Git submodule: OCA sale-workflow 18.0, ghim ở commit e0694c7
ui_tests/                            kịch bản Playwright và script tạo dữ liệu mẫu cho UI test
```

## Clone và cài đặt

Yêu cầu: mã nguồn Odoo 18.0, PostgreSQL, và một Python virtualenv đã cài các thư viện của Odoo (`requirements.txt` trong thư mục Odoo). Mã OCA nằm trong submodule nên cần clone kèm submodule:

```bash
git clone --recurse-submodules https://github.com/NhatMinh205-UIT/odoo18-sale-multi-delivery.git
cd odoo18-sale-multi-delivery
git submodule status        # phải thấy e0694c7bd12d1d286b2a8ebe8e8f0130d1290942 oca/sale-workflow
```

Nếu đã clone mà thiếu submodule: `git submodule update --init`. Submodule được khai báo `shallow` nên chỉ tải commit đã ghim, không tải toàn bộ lịch sử OCA.

Mọi lệnh dưới đây chạy từ **thư mục gốc của repo** (để các đường dẫn tương đối trong `--addons-path` đúng). Đặt `ODOO_HOME` là thư mục chứa `odoo-bin`:

```bash
export ODOO_HOME=/duong/dan/toi/odoo
export ADDONS="$ODOO_HOME/addons,$ODOO_HOME/odoo/addons,oca/sale-workflow,custom_addons"

python "$ODOO_HOME/odoo-bin" -d multi_delivery -i sale_multi_delivery \
  --addons-path="$ADDONS" --stop-after-init
```

Odoo tự cài các module phụ thuộc theo chuỗi `sale_multi_delivery` → `sale_stock_delivery_address` → `sale_procurement_group_by_line` → `sale_stock` → `sale`, `stock`. Thêm `--db_host`, `--db_port`, `--db_user`, `--db_password` nếu PostgreSQL của bạn cần. Để chạy server: bỏ `-i ...` và `--stop-after-init`, thêm `--http-port 8069`.

## Chạy test

Test của addon chạy trên một database mới (tự cài module rồi chạy):

```bash
python "$ODOO_HOME/odoo-bin" -d multi_delivery_test -i sale_multi_delivery \
  --addons-path="$ADDONS" --test-enable --test-tags /sale_multi_delivery --stop-after-init
```

### UI test (Playwright)

UI test điều khiển trình duyệt thật trên một server Odoo đang chạy và cần dữ liệu mẫu. Cài Playwright một lần:

```bash
pip install playwright
playwright install chromium
```

Tạo dữ liệu mẫu (an toàn khi chạy lại), bật server, rồi chạy test với thông tin kết nối đặt qua biến môi trường:

```bash
python "$ODOO_HOME/odoo-bin" shell -d multi_delivery --addons-path="$ADDONS" < ui_tests/seed_demo_data.py
python "$ODOO_HOME/odoo-bin" -d multi_delivery --addons-path="$ADDONS" --http-port 8069   # terminal khác

export ODOO_DB=multi_delivery ODOO_LOGIN=<tài-khoản> ODOO_PASSWORD=<mật-khẩu>
export ODOO_URL=http://localhost:8069      # tùy chọn, mặc định là http://localhost:8069
python ui_tests/ui_test_multi_delivery.py
```

Cách demo bằng tay trên giao diện nằm trong `custom_addons/sale_multi_delivery/README.md`.
