# Kenney 1-Bit Tile Tagger

Kenney 1-bit 타일셋을 개별 타일로 분리하고, VLM(Qwen3-VL)으로 카테고리/설명 + WFC edge 호환성 태그를 자동 부여하는 파이프라인.

## 타일셋 정보

- **소스**: [Kenney 1-Bit Pack](https://kenney.nl/assets/1-bit-pack)
- **타일시트**: `Tilemap/tileset_legacy.png` (543×543px)
- **그리드**: 32×32 = 1024 타일 (16×16px, 1px 간격)
- **TMX 호환**: `Tilemap/*.tmx` 파일의 GID와 매핑됨

## 빠른 시작

### 1. 환경 설정

```bash
# CUDA (NVIDIA GPU) — 권장
pip install -r requirements.txt

# torch CUDA 버전이 아닌 경우 재설치
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### 2. 타일 분리

```bash
python split_tiles.py
```

`tiles/` 디렉토리에 1024개 PNG + `tile_index.json` 생성.

### 3. VLM 태깅

```bash
# 8B 모델 (기본, 24GB+ VRAM 권장)
python tag_tiles.py

# 2B 모델 (8GB+ VRAM 또는 Apple Silicon)
python tag_tiles.py --model 2b

# 체크포인트 무시하고 처음부터
python tag_tiles.py --reset
```

결과: `tile_tags.json`

### 4. 인접 규칙 추출 (TMX 맵 기반)

```bash
python extract_adjacency.py
python extract_adjacency.py --min-count 2   # 최소 2회 이상 관찰된 쌍만
```

`Tilemap/*.tmx` 샘플 맵에서 타일 인접 쌍을 수집하여 `tile_adjacency.json` 생성.
Tiled flip flag(H/V/D)도 구분하여 방향별 이웃 빈도를 기록.

### 5. 타일 에디터

```bash
python tile_editor.py
```

GUI 기반 타일 에디터:
- **팔레트**: 카테고리/검색 필터로 타일 선택
- **맵 캔버스**: 좌클릭 배치, 우클릭 삭제
- **태그 편집**: 선택 타일의 카테고리/설명/edge 수정
- **이웃 추천**: adjacency 데이터 기반 3×3 이웃 미리보기 + 방향별 Top-N 리스트
- **맵→인접 규칙 갱신**: 에디터에서 배치한 맵으로 adjacency 데이터 누적 병합

| 단축키 | 기능 |
|--------|------|
| `Ctrl+Shift+S` (`Cmd+Shift+S`) | 전체 태그 저장 |
| `Ctrl+Shift+A` (`Cmd+Shift+A`) | 맵에서 인접 규칙 갱신 |

## 하드웨어별 예상 시간

| GPU | 모델 | VRAM 사용 | 예상 시간 |
|-----|------|----------|----------|
| **RTX 3090 (24GB)** | **8B** | **~17GB** | **~25분** |
| RTX 3090 (24GB) | 2B | ~5GB | ~10분 |
| Apple Silicon (MPS) | 2B | ~5GB | ~60분 |
| CPU | 2B | ~5GB RAM | ~3시간+ |

## 출력 형식

`tile_tags.json`:

```json
{
  "metadata": {
    "source": "tileset_legacy.png",
    "tile_size": 16,
    "grid": [32, 32],
    "total_possible": 1024
  },
  "total_tagged": 1024,
  "tiles": [
    {
      "id": "tile_0_0",
      "gid": 1,
      "row": 0, "col": 0,
      "pixel_x": 0, "pixel_y": 0,
      "category": "terrain",
      "description": "dark purple ground tile",
      "edges": {
        "top": "solid",
        "bottom": "solid",
        "left": "solid",
        "right": "solid"
      }
    }
  ]
}
```

### 카테고리 종류

`terrain`, `building`, `character`, `item`, `UI`, `decoration`, `nature`, `vehicle`, `weapon`, `tool`, `furniture`, `wall`, `floor`, `door`, `window`, `water`, `sky`, `underground`

### Edge 타입

`empty`, `solid`, `ground_top`, `ground_bottom`, `wall_left`, `wall_right`, `wall_top`, `wall_bottom`, `grass`, `sky`, `water_top`, `water_bottom`, `trunk`, `foliage`, `roof`, `floor`, `platform`, `mixed`

## 파일 구조

```
kenny1bit-tagger/
├── README.md
├── CLAUDE.md                # Claude Code 가이드
├── requirements.txt
├── split_tiles.py           # Stage 1: 타일 분리
├── tag_tiles.py             # Stage 2: VLM 태깅
├── extract_adjacency.py     # Stage 3: TMX 맵에서 인접 규칙 추출
├── tile_editor.py           # GUI 타일 에디터 + 태그 편집 + 인접 규칙 갱신
├── Tilemap/
│   ├── tileset_legacy.png   # 소스 타일시트
│   ├── tileset_colored.tsx  # Tiled 타일셋 정의
│   └── sample_*.tmx        # 샘플 맵
├── Tilesheet/               # 다른 형식의 타일시트
├── tiles/                   # (생성됨) 개별 타일 이미지
├── tile_index.json          # (생성됨) 타일 인덱스
├── tile_tags.json           # (생성됨) 최종 태깅 결과
└── tile_adjacency.json      # (생성됨) 타일 인접 규칙
```

## 중단/재개

태깅 중 중단해도 50타일마다 체크포인트가 저장됩니다. 다시 실행하면 자동으로 이어서 진행합니다.

```bash
# 재개
python tag_tiles.py

# 처음부터 다시
python tag_tiles.py --reset
```
