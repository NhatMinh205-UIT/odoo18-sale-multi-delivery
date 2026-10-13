# sale_multi_delivery

Một đơn bán hàng, nhiều phiếu giao: mỗi dòng đơn hàng có một `Destination Address` riêng (field của addon OCA `sale_stock_delivery_address`). Khi xác nhận đơn, Odoo tạo một phiếu giao cho mỗi địa chỉ.

Addon này chỉ bổ sung hai quy tắc mà OCA chưa có:

- Địa chỉ phải thuộc khách hàng của đơn và không được là địa chỉ hóa đơn hoặc riêng tư (giao diện lọc danh sách chọn, server kiểm tra lại bằng constraint, và kiểm tra lại khi đổi khách hàng).
- Không đổi được địa chỉ của dòng đã có sau khi đơn được xác nhận (giao diện chỉ-đọc, server chặn khi ghi).

## Cài đặt

Addon phụ thuộc OCA `sale-workflow` nhánh `18.0`, ghim ở commit `e0694c7bd12d1d286b2a8ebe8e8f0130d1290942` (`sale_stock_delivery_address` 18.0.1.1.1, `sale_procurement_group_by_line` 18.0.1.0.2). Mã OCA có sẵn trong Git submodule `oca/sale-workflow` ở thư mục gốc của repo.

Cách clone, cấu hình `--addons-path`, cài đặt và chạy test nằm trong `README.md` ở thư mục gốc.

## Demo bằng tay (ứng dụng Sales và Inventory, xuất kho một bước)

1. Contacts: tạo khách hàng `Acme Corporation` với ba liên hệ con loại Delivery Address (Office A, B, C).
2. Sản phẩm `Laptop`: loại Goods, bật Track Inventory, chính sách xuất hóa đơn "Delivered quantities", tồn kho 10.
3. Sales: tạo báo giá mới cho Acme với ba dòng Laptop (4, 3, 3), mỗi dòng chọn một Destination Address. Danh sách địa chỉ chỉ hiện các địa chỉ của Acme.
4. Bấm Confirm. Nút Delivery hiện 3 phiếu giao, mỗi phiếu gửi đúng văn phòng, số lượng 4 + 3 + 3.
5. Validate một phiếu: chỉ số lượng đã giao của dòng tương ứng thay đổi. Validate một phần rồi chấp nhận tạo backorder: backorder giữ nguyên địa chỉ nhận.
6. Bấm Create Invoice: chỉ tính phần số lượng đã giao.
7. Sau khi Confirm, ô Destination Address của các dòng đã có không sửa được.
