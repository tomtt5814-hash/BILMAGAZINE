#!/usr/bin/env bash
# 下载 whisper.cpp Windows 预编译包（优先 Vulkan）+ ggml 模型
set -u
PROXY="http://127.0.0.1:7897"
ROOT="/f/project-bilmassage/tools/whisper"
MODEL="${MODEL:-ggml-small.bin}"
mkdir -p "$ROOT"
cd "$ROOT" || exit 1

echo "[1/4] 解析最新 release tag"
TAG=$(curl -sSL -x "$PROXY" --max-time 60 -o /dev/null -w '%{url_effective}' \
  "https://github.com/ggml-org/whisper.cpp/releases/latest" | sed 's#.*/tag/##')
echo "    tag=$TAG"

echo "[2/4] 查找 Windows 资源文件名"
curl -sSL -x "$PROXY" --max-time 60 \
  "https://github.com/ggml-org/whisper.cpp/releases/expanded_assets/$TAG" \
  | grep -oE 'whisper-bin-x64[^"]*\.zip|whisper-blas-bin-x64[^"]*\.zip' | sort -u | tee assets.txt

ASSET=$(grep -i vulkan assets.txt | head -1)
[ -z "$ASSET" ] && ASSET=$(grep -i 'whisper-bin-x64' assets.txt | head -1)
if [ -z "$ASSET" ]; then echo "!! 未找到 Windows 预编译包"; exit 2; fi
echo "    选择: $ASSET"

echo "[3/4] 下载 $ASSET"
curl -L -x "$PROXY" --max-time 600 -o whisper.zip \
  "https://github.com/ggml-org/whisper.cpp/releases/download/$TAG/$ASSET" || exit 3
ls -lh whisper.zip
python -c "import zipfile;zipfile.ZipFile('whisper.zip').extractall('.')" || exit 4

echo "[4/4] 下载模型 $MODEL"
if [ ! -f "$MODEL" ]; then
  curl -L -x "$PROXY" --max-time 900 -o "$MODEL" \
    "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/$MODEL" || exit 5
fi
ls -lh "$MODEL"

echo "OK: 可执行文件"
find . -maxdepth 3 -iname "whisper-cli.exe" -o -maxdepth 3 -iname "main.exe" | head -5
