# centos 8.1 on digital ocean
# root required

# settings
export DB_PASS=8dJUVBP1ZNqM9w==
export WORKING_DIRECTORY=/root
export PROJECT_DIR=$WORKING_DIRECTORY/telegram_filtered_feed

# set locale
export LANG=en_US.utf8
localectl set-locale LANG=en_US.UTF-8

# ensure all system packages are up-to-date
dnf update -y

# install deps 
dnf install -y git

# add htop for convenience
dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
dnf install -y htop

# install python3.7
dnf install -y wget gcc openssl-devel bzip2-devel make libffi-devel sqlite-devel

cd /usr/src
wget https://www.python.org/ftp/python/3.7.0/Python-3.7.0.tgz
tar xzf Python-3.7.0.tgz

cd /usr/src/Python-3.7.0
./configure --enable-optimizations
make altinstall

ln -s /usr/local/bin/python3.7 /usr/bin/python3.7
ln -s /usr/local/bin/pip3.7 /usr/bin/pip3.7

rm -f /usr/src/Python-3.7.0.tgz

# config journalctl
## if this directory is created its gonna be used. by default its on a larger mounted drive, so logs are gonna be bigger this way
mkdir -p /var/log/journal
systemctl restart systemd-journald

## this is alternative to mkdir, but I assume mkdir is safer
#sed -i 's/#Storage=auto/Storage=persistent/g' /etc/systemd/journald.conf

# postgres
## add repo
yum -y install https://download.postgresql.org/pub/repos/yum/reporpms/EL-8-x86_64/pgdg-redhat-repo-latest.noarch.rpm

## disable builtin
dnf -qy module disable postgresql

## install
dnf -y install postgresql12 postgresql12-server postgresql12-devel libpq-devel

## init
/usr/pgsql-12/bin/postgresql-12-setup initdb
systemctl enable --now postgresql-12

## user & auth
sudo -u postgres createuser root
sudo -u postgres psql -c "ALTER USER root with superuser"
psql feed -c "ALTER USER root PASSWORD '$DB_PASS'"
sed -i 's/      ident/      md5/g' /var/lib/pgsql/12/data/pg_hba.conf
systemctl restart postgresql-12

# clone & prepare project
cd $WORKING_DIRECTORY
git clone git@github.com:delimbetov/telegram_filtered_feed.git
cd $PROJECT_DIR
git checkout dev

## venv
python3 -m venv venv
source $PROJECT_DIR/venv/bin/activate

## requirements
pip3.7 install -r requirements.txt

## db schema
$PROJECT_DIR/etc/dbcreate.sh

## ALTERNATIVE is dump & load
# pg_dump feed > dump.sql
# sed -i 's/kirilldelimbetov/root/g' ./dump.sql
# psql feed < dump.sql

## config (change db user&pass)
sed -i 's/kirilldelimbetov/root/g' $PROJECT_DIR/forwarder/config.py
sed -i 's/db_password = None/db_password = "'$DB_PASS'"/g' $PROJECT_DIR/forwarder/config.py
sed -i 's/kirilldelimbetov/root/g' $PROJECT_DIR/feed_bot/config.py
sed -i 's/db_password = None/db_password = "'$DB_PASS'"/g' $PROJECT_DIR/feed_bot/config.py

## put service scripts in place
cp $PROJECT_DIR/etc/{feedbot,forwarder@,resolver}.service /etc/systemd/system

# run: to establish session I have to type phone number & code
cd $PROJECT_DIR
export PYTHONPATH=$PYTHONPATH:$PWD/

## before running cmds CD to working dir, usually the dir of the subproject
## forwarder0
python3.7 ../main.py YOUR_OWN_API_ID YOUR_OWN_API_HASH 0 421

## forwarder1
python3.7 ../main.py YOUR_OWN_API_ID YOUR_OWN_API_HASH 422 900

## forwarder2
python3.7 ../main.py YOUR_OWN_API_ID YOUR_OWN_API_HASH 901 1380

## resolver
python3.7 ./main.py YOUR_OWN_API_ID YOUR_OWN_API_HASH

## prepare working dirs for multi forwarders
## dirs must match forwarder run params
mkdir -p $PROJECT_DIR/forwarder/forwarder0_421
mkdir -p $PROJECT_DIR/forwarder/forwarder422_900
mkdir -p $PROJECT_DIR/forwarder/forwarder901_1380

# run services
systemctl daemon-reload
systemctl restart feedbot forwarder@0_421 forwarder@422_900 forwarder@901_1380 resolver
systemctl status feedbot forwarder@0_421 forwarder@422_900 forwarder@901_1380 resolver

TODO:
- use user instead of root
