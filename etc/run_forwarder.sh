echo "Preparing env vars"
source ../../etc/env
echo "Enabling venv"
source ../../venv/bin/activate

# replace _ with whitespace
export RAW_INTERVALS_ARG="$1"
export INTERVALS_ARG=${RAW_INTERVALS_ARG//_/ }

echo "Starting forwarder"
python3.7 $PROJECTPATH/forwarder/main.py $FORWARDER_ARGS $INTERVALS_ARG
