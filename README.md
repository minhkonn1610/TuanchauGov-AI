# TuanchauGov AI

**Hệ thống AI hỗ trợ tra cứu và hỏi đáp tài liệu hành chính**

TuanchauGov AI là ứng dụng hỗ trợ người dùng tìm kiếm, tra cứu và hỏi đáp bằng tiếng Việt trên các tài liệu PDF. Hệ thống kết hợp truy xuất thông tin, xử lý ngôn ngữ tự nhiên và mô hình ngôn ngữ lớn (LLM) nhằm giúp người dùng tiếp cận nội dung tài liệu thuận tiện hơn, đồng thời cung cấp thông tin nguồn để kiểm tra câu trả lời.

Sản phẩm hướng tới bài toán nâng cao hiệu quả tra cứu tài liệu trong hoạt động quản lý và điều hành tại cơ quan hành chính địa phương.

## 1. Mục tiêu

- Hỗ trợ tra cứu thông tin từ tài liệu PDF bằng câu hỏi tiếng Việt.
- Kết hợp nhiều phương pháp truy xuất để tìm nội dung liên quan đến câu hỏi.
- Cung cấp câu trả lời kèm thông tin nguồn để người dùng đối chiếu với tài liệu.
- Hỗ trợ nhận diện thông tin ở phần đầu văn bản PDF bằng cơ chế OCR chọn lọc.
- Xây dựng cơ sở kỹ thuật phục vụ việc thử nghiệm và phát triển ứng dụng AI cho nghiệp vụ hành chính.

## 2. Chức năng chính

### 2.1. Tải lên và quản lý tài liệu

Người dùng có thể tải lên tài liệu PDF, chọn tài liệu phục vụ cuộc hội thoại và làm việc với các tài liệu đã có trong hệ thống.

### 2.2. Hỏi đáp theo nội dung tài liệu

Hệ thống hỗ trợ ba chế độ xử lý câu hỏi:

- **Fast:** Kết hợp tìm kiếm vector và tìm kiếm toàn văn trên các đoạn tài liệu, sau đó hợp nhất và xếp hạng kết quả.
- **Balanced:** Khai thác thông tin thực thể và quan hệ trong đồ thị tri thức, trong phạm vi tài liệu được chọn.
- **Deep:** Phân tách câu hỏi thành các truy vấn phụ, thực hiện truy xuất và tổng hợp kết quả.

Các chế độ được thiết kế để phục vụ những nhu cầu tra cứu khác nhau. Độ chính xác của câu trả lời vẫn cần được đánh giá trên bộ tài liệu và tình huống sử dụng thực tế.

### 2.3. Truy xuất nguồn và Evidence

Hệ thống hỗ trợ hiển thị nguồn tham khảo cho câu trả lời, mở tài liệu PDF liên quan và trình bày vùng bằng chứng để người dùng kiểm tra ngữ cảnh.

Evidence giúp người dùng đối chiếu nội dung do AI cung cấp với tài liệu nguồn. Người dùng vẫn cần xem xét ngữ cảnh gốc trước khi sử dụng thông tin cho công việc nghiệp vụ.

### 2.4. OCR chọn lọc phần đầu văn bản

Hệ thống có cơ chế OCR chọn lọc để hỗ trợ nhận diện thông tin trên phần đầu trang đầu tiên của PDF trong những trường hợp cần thiết.

Theo kết quả kiểm thử trên PDF mẫu, bộ kiểm thử đã xác nhận các điều kiện sau:

- PDF Loader hoàn thành.
- Nhận diện được số văn bản.
- Nhận diện được ngày văn bản.
- Giữ được dấu phân trang.
- Kết quả tổng thể: `SELECTIVE_HEADER_OCR_TEST: PASS`.

Kết quả này chỉ phản ánh bài kiểm thử trên PDF mẫu, không đồng nghĩa với việc mọi định dạng văn bản đều đã được kiểm thử.

### 2.5. Lịch sử hội thoại và bộ nhớ

Hệ thống sử dụng Redis để lưu trữ dữ liệu hội thoại ngắn hạn và Neo4j cho các thành phần bộ nhớ dài hạn, truy xuất thông tin và quan hệ liên quan.

Các chức năng lưu trữ, truy hồi và xử lý bộ nhớ phụ thuộc vào cấu hình cũng như trạng thái hoạt động của các dịch vụ liên quan.

## 3. Công nghệ sử dụng

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Backend | Python, FastAPI, Uvicorn | Xây dựng API và xử lý yêu cầu từ giao diện |
| Frontend | HTML, CSS, JavaScript | Giao diện tải tài liệu và hỏi đáp |
| LLM Adapter | LiteLLM | Kết nối với các dịch vụ mô hình ngôn ngữ tương thích |
| Cơ sở dữ liệu đồ thị | Neo4j | Lưu trữ đồ thị tri thức và các cấu trúc dữ liệu liên quan |
| Bộ nhớ ngắn hạn | Redis | Lưu trữ lịch sử hội thoại và dữ liệu phiên |
| Xử lý PDF | MarkItDown và PyMuPDF | Hỗ trợ chuyển đổi và xử lý tài liệu PDF |
| Chia đoạn | LangChain Text Splitters và SemanticChunker | Phân chia nội dung tài liệu theo cấu trúc và ngữ nghĩa |
| Embedding và xếp hạng | Sentence Transformers | Hỗ trợ biểu diễn và xếp hạng nội dung truy xuất |
| OCR | PaddleOCR, PaddlePaddle, PaddleX | Hỗ trợ nhận diện thông tin trên tài liệu |

## 4. Kiến trúc hệ thống

Luồng xử lý tài liệu tổng quát:

1. Người dùng tải lên hoặc chọn tài liệu PDF.
2. Hệ thống xử lý tài liệu và chuyển nội dung sang dạng có thể phân tích.
3. Nội dung được chia thành các đoạn phục vụ truy xuất.
4. Các thành phần embedding, chỉ mục tìm kiếm và đồ thị tri thức được sử dụng theo cấu hình của hệ thống.
5. Khi có câu hỏi, hệ thống truy xuất nội dung phù hợp trong phạm vi tài liệu đang hoạt động.
6. Mô hình ngôn ngữ tổng hợp câu trả lời và thông tin nguồn.
7. Giao diện hiển thị câu trả lời, nguồn và các thành phần Evidence tương ứng.

Luồng OCR chọn lọc sử dụng một môi trường Python riêng để hạn chế ảnh hưởng của các thư viện OCR đến môi trường backend chính.

## 5. Cấu trúc thư mục

Cấu trúc dưới đây mô tả các thành phần mã nguồn và cấu hình chính. Một số thư mục dữ liệu hoặc cache có thể chỉ xuất hiện tùy theo môi trường triển khai.

```text
TuanchauGov-AI/
│
├── app/                                  # Backend và logic xử lý AI
│   ├── main.py                           # Ứng dụng FastAPI và các API của hệ thống
│   ├── core/
│   │   └── config.py                     # Cấu hình embedding, Neo4j, LiteLLM và truy xuất
│   ├── ingestion/                        # Tiếp nhận và xử lý tài liệu
│   │   ├── pdf_loader.py                 # Chuyển đổi PDF thành Markdown
│   │   ├── header_ocr.py                 # Điều phối OCR chọn lọc phần đầu văn bản
│   │   └── ocr_header_worker.py          # Worker thực thi OCR trong môi trường riêng
│   ├── chunking/
│   │   └── chunker.py                    # Chia đoạn Markdown và ngữ nghĩa
│   ├── providers/                        # Dịch vụ AI và xử lý ngôn ngữ
│   │   ├── embedding.py                  # Tạo embedding cho nội dung
│   │   ├── reranking.py                  # Xếp hạng lại kết quả truy xuất
│   │   ├── context_compressor.py         # Nén ngữ cảnh trước khi gửi đến mô hình
│   │   └── litellm_client.py             # Kết nối mô hình ngôn ngữ qua LiteLLM
│   ├── extraction/                       # Trích xuất thông tin và quan hệ
│   │   ├── entity_extractor.py           # Trích xuất thực thể và quan hệ bằng LLM
│   │   └── community_builder.py          # Xây dựng cộng đồng thực thể và bản tóm tắt
│   ├── graph/
│   │   └── neo4j_store.py                # Lưu trữ đồ thị tài liệu trong Neo4j
│   ├── retrieval/                        # Các phương thức truy xuất
│   │   ├── naive.py                      # Tìm kiếm vector/toàn văn và hợp nhất kết quả
│   │   └── local.py                      # Truy xuất theo thực thể và ngữ cảnh đồ thị
│   ├── reasoning/                        # Tổng hợp và lập kế hoạch trả lời
│   │   ├── answer_generator.py           # Tạo câu trả lời từ ngữ cảnh truy xuất
│   │   └── deepsearch.py                 # Lập kế hoạch tìm kiếm theo truy vấn phụ
│   ├── pipeline/                         # Các luồng xử lý chính
│   │   ├── ingest.py                     # Tiếp nhận và lập chỉ mục tài liệu
│   │   ├── naive_chat.py                 # Luồng hỏi đáp Fast
│   │   ├── local_chat.py                 # Luồng hỏi đáp Balanced
│   │   └── graph_builder.py              # Xây dựng dữ liệu đồ thị tri thức
│   └── memory/                           # Bộ nhớ hội thoại
│       ├── config.py                     # Cấu hình bộ nhớ
│       ├── shortterm.py                  # Lịch sử hội thoại ngắn hạn qua Redis
│       └── longterm/                     # Bộ nhớ dài hạn trong Neo4j
│           ├── core.py                   # Điều phối bộ nhớ dài hạn
│           ├── neo4j_memory_store.py     # Lưu trữ bộ nhớ trong Neo4j
│           ├── recall.py                 # Truy hồi bộ nhớ theo vector và từ khóa
│           ├── enrichment.py             # Bổ sung thông tin cho bộ nhớ
│           ├── consolidation.py          # Tổng hợp và quản lý vòng đời bộ nhớ
│           └── scheduler.py              # Lập lịch tác vụ bảo trì bộ nhớ
│
├── web/                                  # Frontend của ứng dụng
│   ├── index.html                        # Khung HTML và cấu trúc giao diện
│   ├── app.js                            # Tương tác giao diện, hội thoại và Evidence
│   └── styles.css                        # Kiểu dáng và bố cục giao diện
│
├── prompts/                              # Các prompt phục vụ xử lý tiếng Việt
│   ├── answer.vi.md                      # Prompt tạo câu trả lời
│   ├── community_summary.vi.md            # Prompt tóm tắt cộng đồng thực thể
│   ├── deepsearch_planner.vi.md          # Prompt lập kế hoạch Deep Search
│   ├── entity_extraction.vi.md           # Prompt trích xuất thực thể
│   └── memory_enrichment.vi.md            # Prompt bổ sung bộ nhớ
│
├── data/
│   ├── raw/
│   │   └── pdf/                          # Tài liệu PDF đầu vào
│   ├── processed/                        # Nội dung tài liệu đã chuyển đổi
│   └── eval/                             # Dữ liệu đánh giá, nếu được sử dụng
│
├── scripts/                              # Script thiết lập và kiểm thử
│   ├── Setup-ChatWithTB-HeaderOCR-Env.ps1 # Thiết lập môi trường OCR riêng
│   ├── Start-ChatWithTB-HeaderOCR.ps1     # Khởi chạy backend kèm cấu hình OCR
│   ├── Test-ChatWithTB-HeaderOCR.ps1      # Kiểm thử OCR chọn lọc
│   ├── test_header_ocr_sample.py          # Kiểm thử trên PDF mẫu
│   └── requirements-ocr.txt               # Thư viện dành riêng cho OCR
│
├── docs/                                 # Tài liệu và hình minh họa
├── models_cache/                         # Cache mô hình cục bộ, nếu được sử dụng
├── docker-compose.yml                    # Cấu hình Neo4j, Redis và Redis Insight
├── requirements.txt                      # Các thư viện Python chính
├── .env.example                          # Mẫu cấu hình môi trường
├── .gitignore                            # Quy tắc bỏ qua file trong Git
└── README.md                             # Tài liệu giới thiệu và hướng dẫn sử dụng
```

**Lưu ý về cấu trúc:**

- Cây thư mục mô tả các thành phần chính, không đảm bảo mọi thư mục dữ liệu hoặc cache đều được tạo sẵn trong mỗi môi trường.
- `.venv/` và `.venv-ocr/` là môi trường Python cục bộ; thông thường không đưa các thư mục này lên Git.
- `.env` có thể chứa thông tin nhạy cảm và không nên được đưa vào kho mã nguồn công khai.
- `models_cache/`, dữ liệu PDF nội bộ và bản backup cần được quản lý riêng.
- Một số tên script OCR được giữ nguyên để tương thích với các lệnh thiết lập và kiểm thử hiện có.

## 6. Yêu cầu môi trường

- Windows hoặc môi trường tương thích có thể chạy Python và Docker.
- Python 3.12 trở lên theo yêu cầu của dự án.
- Docker Desktop và Docker Compose.
- Neo4j 5.x.
- Redis.
- Một endpoint LLM tương thích với LiteLLM cùng thông tin xác thực được cấu hình riêng.
- Các thư viện Python được khai báo trong `requirements.txt`.

OCR chọn lọc cần môi trường Python riêng `.venv-ocr` với các phiên bản thư viện được khai báo trong `scripts/requirements-ocr.txt`.

## 7. Hướng dẫn chạy trên Windows

Các lệnh dưới đây được thực hiện từ thư mục gốc của dự án trong PowerShell.

### 7.1. Chuẩn bị môi trường Python chính

Tạo môi trường ảo nếu dự án chưa có:

```powershell
python -m venv .venv
```

Kích hoạt môi trường:

```powershell
.\.venv\Scripts\Activate.ps1
```

Cài đặt thư viện:

```powershell
python -m pip install -r requirements.txt
```

Nếu môi trường `.venv` đã tồn tại và hoạt động bình thường, không cần tạo lại chỉ vì thay đổi tên thương hiệu.

### 7.2. Cấu hình môi trường

Sao chép file mẫu `.env.example` thành `.env` bằng PowerShell tại thư mục gốc của dự án:

```powershell
Copy-Item .env.example .env
```

Chỉ thực hiện lệnh này khi file `.env` chưa tồn tại.

Mở file `.env` và thay giá trị mẫu `CHANGE_ME_TO_A_STRONG_PASSWORD` trong biến `NEO4J_PASSWORD` bằng mật khẩu riêng đủ mạnh. Không cần nhập lại mật khẩu vào `NEO4J_AUTH`, vì biến này tham chiếu đến `NEO4J_PASSWORD`.

Tiếp tục cấu hình `LLM_API_BASE`, `LLM_API_KEY` và các biến cần thiết theo dịch vụ AI được sử dụng.

Không công khai file `.env` hoặc đưa thông tin xác thực thật lên GitHub. Chỉ sử dụng `.env.example` làm mẫu cấu hình.

### 7.3. Khởi động Neo4j và Redis

Kiểm tra Docker Desktop đã sẵn sàng, sau đó chạy:
Trước khi khởi động Docker Compose, hãy cấu hình biến `NEO4J_AUTH`
trong file `.env` cục bộ của bản phát hành theo định dạng:

`NEO4J_AUTH=neo4j/mat_khau_rieng_cua_ban`

Hãy thay phần mật khẩu mẫu bằng mật khẩu riêng đủ mạnh. Không đưa
file `.env` lên GitHub.

Nếu sử dụng một Neo4j đã có dữ liệu, hãy dùng thông tin xác thực
hiện tại của cơ sở dữ liệu. Thay đổi `NEO4J_AUTH` không tự đặt lại
mật khẩu của một cơ sở dữ liệu đã khởi tạo.
```powershell
docker compose up -d neo4j redis redis-insight
```

Các địa chỉ phục vụ kiểm tra cục bộ theo cấu hình hiện tại:

- Neo4j Browser: `http://localhost:7474`
- Redis Insight: `http://localhost:5540`

Khi kết nối Redis từ Redis Insight trong cùng mạng Docker, sử dụng tên dịch vụ `redis` và cổng `6379`.

**Lưu ý:** Nếu hệ thống đã có container sử dụng cùng tên, cổng hoặc volume, hãy kiểm tra trạng thái hiện tại trước khi khởi động thêm cấu hình khác.

### 7.4. Khởi động backend

Từ thư mục gốc của dự án:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Khi backend khởi động thành công, mở `http://127.0.0.1:8000`.

Để kiểm tra trạng thái backend, truy cập `http://127.0.0.1:8000/health`.

### 7.5. Thiết lập và chạy OCR chọn lọc

Chỉ thực hiện thiết lập môi trường OCR riêng khi môi trường này chưa tồn tại hoặc cần cài đặt mới.

Chạy script thiết lập:

```powershell
.\scripts\Setup-ChatWithTB-HeaderOCR-Env.ps1
```

Script thiết lập môi trường `.venv-ocr` riêng và cài đặt các phụ thuộc OCR theo `scripts/requirements-ocr.txt`. Quá trình này có thể tải xuống các gói và mô hình cần thiết.

Để khởi chạy backend với cấu hình OCR theo script:

```powershell
.\scripts\Start-ChatWithTB-HeaderOCR.ps1
```

Script này khởi chạy backend trên cổng `8000`. Không chạy nó đồng thời với một backend khác đang chiếm cùng cổng.

Để kiểm thử OCR trên PDF mẫu, cần có đúng một file phù hợp với mẫu `12904*.signed.pdf` trong `data/raw/pdf/`. Sau đó chạy:

```powershell
.\scripts\Test-ChatWithTB-HeaderOCR.ps1
```

Bài kiểm thử sẽ dừng nếu không tìm thấy đúng một file mẫu hoặc môi trường OCR chưa đáp ứng yêu cầu.

## 8. Sử dụng ứng dụng

1. Mở giao diện tại `http://127.0.0.1:8000`.
2. Tải lên tài liệu PDF hoặc chọn tài liệu đã có trong hệ thống.
3. Tạo hoặc mở một cuộc hội thoại.
4. Chọn chế độ hỏi đáp Fast, Balanced hoặc Deep.
5. Đặt câu hỏi bằng tiếng Việt.
6. Kiểm tra câu trả lời cùng các nguồn được cung cấp.
7. Mở Evidence hoặc tài liệu PDF để đối chiếu ngữ cảnh khi cần.

## 9. Lưu ý về độ tin cậy và triển khai

- Câu trả lời của AI cần được đối chiếu với tài liệu nguồn, đặc biệt khi sử dụng cho nghiệp vụ hành chính.
- Kết quả kiểm thử trên một tài liệu mẫu không chứng minh hệ thống chính xác với mọi loại PDF.
- Trước khi đưa ứng dụng vào sử dụng thực tế, cần đánh giá chất lượng truy xuất, độ chính xác của câu trả lời, kiểm soát truy cập, bảo vệ dữ liệu và khả năng vận hành.
- Trước khi công khai kho mã nguồn, cần rà soát `.env`, thông tin xác thực, dữ liệu tài liệu, cache, file backup và lịch sử Git.
- Cấu hình Docker dành cho phát triển và thử nghiệm cần được xem xét lại trước khi sử dụng trong môi trường chính thức.

## 10. Hướng phát triển

Các hướng có thể tiếp tục nghiên cứu và hoàn thiện gồm:

- Cải thiện khả năng truy xuất thông tin trên đồ thị tri thức.
- Đánh giá và nâng cao khả năng xác định khi nào Deep Search đã thu thập đủ thông tin.
- Cải thiện cơ chế lưu đệm embedding, kết quả truy xuất và câu trả lời.
- Mở rộng bộ dữ liệu kiểm thử để đánh giá độ chính xác trên nhiều loại tài liệu hành chính.
- Hoàn thiện quy trình triển khai, giám sát và bảo trì trong môi trường sử dụng thực tế.
