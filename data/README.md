# Thư mục Dữ liệu Thử nghiệm (Test Instances)

Thư mục này chứa các bộ dữ liệu test (từ `sample_01.txt` đến `sample_09.txt`) cho bài toán **Share-a-Ride Problem (SARP)**.

---

## 1. Danh sách các file test mẫu

* `sample_01.txt`
* `sample_02.txt`
* `sample_03.txt`
* `sample_04.txt`
* `sample_05.txt`
* `sample_06.txt`
* `sample_07.txt`
* `sample_08.txt`
* `sample_09.txt`

*(Cùng 2 file `sample_01_small.txt` và `sample_02_medium.txt` để trống dự phòng)*

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
# Chạy với test bất kỳ (ví dụ sample_01.txt) với giới hạn 5s
python main.py --time-limit 5 data/sample_01.txt

# Chạy với ngân sách thời gian chuẩn (285s)
python main.py data/sample_01.txt output.txt
```
