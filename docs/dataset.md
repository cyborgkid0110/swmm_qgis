### Dữ liệu và cấu trúc dữ liệu cho mô hình thủy lực

| Nhóm dữ liệu | Dữ liệu cụ thể | Định dạng/Cấu trúc | Ghi chú/Giải thích |
|--------------|----------------|--------------------|-------------------|
| **1. Địa hình & Dữ liệu không gian** | Mô hình số độ cao (DEM/LiDAR) độ phân giải cao (≥5m, lý tưởng 1m) | Raster (GeoTIFF, .asc) | Xác định hướng dòng chảy bề mặt và vùng dễ ngập |
| | Bản đồ địa hình (đường đồng mức, điểm cao độ) | Vector (Shapefile, .dwg, .dxf) | Bổ sung cho DEM, đặc biệt ở đô thị |
| | Bản đồ sử dụng đất / lớp phủ | Vector/Raster (Shapefile) | Xác định hệ số nhám (Manning n) và khả năng thấm |
| **2. Mạng sông, hồ, kênh** | Mạng sông, kênh, mương (tim tuyến, mặt cắt, cao độ đáy, bờ) | Vector (Shapefile, .dwg) + attributes | Dữ liệu nền cho dòng chảy kênh hở |
| | Hồ, hồ điều hòa, hồ chứa (cao độ đáy, mực nước, dung tích) | Vector + attributes | Điều tiết thoát nước và trữ nước |
| **3. Hệ thống thoát nước đô thị** | Mạng cống (vị trí, chiều dài, đường kính, độ dốc, invert, hướng dòng) | Line vector (Shapefile, .dwg) | Cần kiểm tra đảm bảo liên thông & nhất quán thủy lực |
| | Hố ga, giếng tách dòng (vị trí, cao độ, kích thước) | Point vector (Shapefile) | Kết nối nước mặt và hệ thống ngầm |
| | Trạm bơm (vị trí, công suất, vận hành) | Point vector (Shapefile) | Điều khiển dòng trong mạng cống |
| | Cửa xả (vị trí, cao độ, khả năng xả) | Point vector (Shapefile) | Điểm xả ra nguồn tiếp nhận |
| | Đập, cống, công trình thủy lực (kích thước, cao trình đỉnh, vận hành) | Vector + thuộc tính chi tiết | Điều khiển dòng chảy và mực nước |
| **4. Thủy văn, khí tượng & biên** | Chuỗi mưa (phút/giờ từ trạm tự động) | Time series (.csv, .xlsx) | Đầu vào chính cho mô hình ngập |
| | Mực nước, lưu lượng biên sông (giờ/ngày) | Tables (.csv, .xlsx) | Điều kiện biên thượng/hạ lưu |
| | Bốc hơi, nhiệt độ, độ ẩm | Tables (.csv, .xlsx) | Dùng cho mô hình mưa–dòng chảy |
| **5. Nguồn ô nhiễm (nếu có)** | Nguồn xả (KCN, làng nghề, dân cư) | Point vector (.shp) | Dùng cho mô hình chất lượng nước |
| | Nồng độ ô nhiễm (COD, BOD, TSS, N, P) | Tables (.csv, .xlsx) | Đầu vào chất lượng nước |

> **Note:** Chất lượng mô hình thủy lực phụ thuộc rất lớn vào chất lượng dữ liệu đầu vào.