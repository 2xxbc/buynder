#!/bin/bash
# Nightly market sweep — refreshes prices for the Movers page
cd /home/bc_2xx/pokemarket || exit 1
source venv/bin/activate

echo "=== Sweep started $(date) ==="
python -u sync_market.py
echo "=== Sweep finished $(date) ==="

# Re-check images weekly (Sundays only)
if [ "$(date +%u)" -eq 7 ]; then
  echo "=== Image check started $(date) ==="
  python -u check_images.py --all
  echo "=== Image check finished $(date) ==="
fi
