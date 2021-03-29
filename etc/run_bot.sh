echo "Preparing env vars"
source ../etc/env
echo "Enabling venv"
source ../venv/bin/activate

echo "Starting bot"
python3.7 ./main.py $BOT_ARGS
