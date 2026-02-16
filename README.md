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
kenny1bit/
├── README.md
├── requirements.txt
├── split_tiles.py           # 타일 분리
├── tag_tiles.py             # VLM 태깅
├── Tilemap/
│   ├── tileset_legacy.png   # 소스 타일시트
│   ├── tileset_colored.tsx  # Tiled 타일셋 정의
│   └── sample_*.tmx        # 샘플 맵
├── Tilesheet/               # 다른 형식의 타일시트
├── tiles/                   # (생성됨) 개별 타일 이미지
├── tile_index.json          # (생성됨) 타일 인덱스
└── tile_tags.json           # (생성됨) 최종 태깅 결과
```

## 중단/재개

태깅 중 중단해도 50타일마다 체크포인트가 저장됩니다. 다시 실행하면 자동으로 이어서 진행합니다.

```bash
# 재개
python tag_tiles.py

# 처음부터 다시
python tag_tiles.py --reset
```
