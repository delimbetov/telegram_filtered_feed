echo "Preparing env vars"
source ../etc/env
echo "Enabling venv"
source ../venv/bin/activate

echo "Starting resolver"
python3.7 ./main.py $RESOLVER_ARGS
