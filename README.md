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
custom_addons/sale_multi_delivery/   addon (manifest, models, views, tests, README hướng dẫn cài và demo)
ui_tests/                            kịch bản Playwright chạy trên giao diện Odoo
```

Cách cài đặt và các bước demo nằm trong `custom_addons/sale_multi_delivery/README.md`.
