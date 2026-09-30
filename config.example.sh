# Copy to .local/config.sh and fill in your own values. This file is sourced
# by Scripts/madeira-runtime.sh; .local/ is never published.
export MEWGENICS_CACHE="/Volumes/Work/caches/meowgenics-ipad"
export DEVELOPMENT_TEAM="YOUR_TEAM_ID"
export MEWGENICS_BUNDLE_ID="com.yourname.mewgenics"
export DEVICE_UDID="YOUR_IPAD_UDID"
# Your own complete Windows game installation. Never commit its contents.
export MEWGENICS_GAME_DIR="$ROOT/Mewgenics-exe"
# Optional: your own opaque 1024x1024 PNG. Omit for a generated neutral icon.
# export MEWGENICS_APP_ICON="$ROOT/.local/private-assets/icon.png"
# export JOBS=12
