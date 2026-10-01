# 블로그 자동 임시저장

업체별 꾸밈 프리셋 + 네이버 계정을 저장해 두면, 원고(hwpx/txt)만 넣었을 때
AI 꾸밈(Gemini 무료) → 해시태그 → 로그인 → 작성 → 태그 → 임시저장까지 자동으로 하는 윈도우·맥 프로그램.

- 사용법: [docs/사용법.txt](docs/사용법.txt)
- 내려받기: 이 저장소의 **Releases**에서 윈도우/맥 파일
- 새 버전 만들기: `app/common.py`의 `APP_VERSION`을 올리고 `v1.0.1` 같은 태그를 push → 윈도우·맥이 함께 빌드되어 같은 릴리스에 올라감

## 구조
| 파일 | 역할 |
|---|---|
| `app/main.py` | 시작점. 로컬 서버를 띄우고 Edge/Chrome 앱 창으로 화면을 연다 |
| `app/web/` | 화면 (기존 "블로그 원고 서식 도구" 레이아웃·꾸밈 로직 이식) |
| `app/server.py` | 화면 ↔ 프로그램 통신, 업로드 작업 큐 |
| `app/store.py` | 구글 드라이브 `NaverBlogHelper/data.json` 동기화, 암호화 |
| `app/ai.py` | Gemini API |
| `app/naver.py` | 네이버 로그인·작성·태그·임시저장 자동화 (Playwright) |
| `app/selectors.json` | 네이버 화면 요소 선택자 (드라이브 폴더의 selectors.json으로 덮어쓰기 가능) |

## 개발 실행
```
pip install -r requirements.txt
python app/main.py
```
