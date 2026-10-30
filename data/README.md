# Thư mục Dữ liệu Thử nghiệm (Test Instances)

Thư mục này chứa các bộ dữ liệu mẫu định dạng chuẩn cho bài toán **Share-a-Ride Problem (SARP)** để Thầy và người chấm thi có thể chạy thử nghiệm và kiểm tra thuật toán ngay lập tức.

---

## 1. Danh sách các bộ test mẫu

| File | Số xe ($K$) | Khách ($N$) | Kiện ($M$) | Tổng đỉnh ($V$) | Thời gian chạy đề xuất | Mục đích thử nghiệm |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `sample_01_small.txt` | 2 | 2 | 1 | 8 | 1 - 3 giây | Kiểm tra luồng chạy cơ bản, ràng buộc đón/trả và ghép khách + hàng |
| `sample_02_medium.txt` | 3 | 4 | 3 | 17 | 3 - 5 giây | Kiểm tra phối hợp đa xe, cửa sổ thời gian (Time Windows) và dung lượng tải (Capacity) |

---

## 2. Cấu trúc dữ liệu trong từng file test

Tất cả các file đều tuân thủ định dạng chuỗi token số nguyên:
1. **Dòng 1**: `K N M`
   - $K$: Số xe taxi.
   - $N$: Số yêu cầu đón/trả hành khách.
   - $M$: Số yêu cầu giao nhận bưu kiện.
   - Tổng số đỉnh trong đồ thị: $V = K + 2N + 2M$.
2. **K dòng tiếp theo**: Mỗi dòng gồm 2 số `depot capacity` là đỉnh xuất phát và tải trọng tối đa của xe $k$.
3. **N dòng tiếp theo**: Mỗi dòng gồm 6 số cho 1 hành khách:
   `p d e_t l_t s_t rev`
   - `p`, `d`: Điểm đón (pickup) và điểm trả (dropoff).
   - `e_t`, `l_t`: Cửa sổ thời gian (thời điểm sớm nhất đón, muộn nhất trả).
   - `s_t`: Thời gian phục vụ tại điểm đón/trả.
   - `rev`: Doanh thu nếu phục vụ.
4. **M dòng tiếp theo**: Mỗi dòng gồm 9 số cho 1 bưu kiện:
   `p d w ep lp ed ld s_t rev`
   - `p`, `d`: Điểm lấy hàng và điểm giao hàng.
   - `w`: Khối lượng hàng (chiếm tải trọng xe).
   - `ep`, `lp`: Cửa sổ thời gian lấy hàng (early pickup, late pickup).
   - `ed`, `ld`: Cửa sổ thời gian giao hàng (early dropoff, late dropoff).
   - `s_t`: Thời gian bốc dỡ tại mỗi điểm.
   - `rev`: Doanh thu khi hoàn thành giao kiện.
5. **Ma trận thời gian di chuyển ($V \times V$)**:
   - Gồm $V$ hàng, mỗi hàng $V$ số nguyên: `travel_time[u][v]`.
6. **Ma trận chi phí di chuyển ($V \times V$)**:
   - Gồm $V$ hàng, mỗi hàng $V$ số nguyên: `travel_cost[u][v]`.

---

## 3. Lệnh chạy nhanh với các bộ test

```bash
# Chạy bộ test nhỏ (Small)
python main.py --time-limit 2 data/sample_01_small.txt

# Chạy bộ test vừa (Medium)
python main.py --time-limit 3 data/sample_02_medium.txt

# Chạy và lưu kết quả ra file output.txt
python main.py --time-limit 5 data/sample_02_medium.txt output.txt
```
