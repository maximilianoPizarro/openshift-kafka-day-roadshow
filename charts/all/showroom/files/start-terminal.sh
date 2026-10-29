#!/bin/bash
# Prepare the shared image defaults, then start ttyd with one process per browser.
# URL arg (?arg=userN) is appended by ttyd and selects that user's home.
set -eu

export USER=lab-user
export HOME=/home/lab-user

if [ -w /etc/passwd ]; then
  grep -v '^lab-user:' /etc/passwd > /tmp/passwd || true
  echo "lab-user:x:$(id -u):0:lab-user user:/home/lab-user:/bin/bash" >> /tmp/passwd
  cat /tmp/passwd > /etc/passwd
  rm -f /tmp/passwd
fi

if [ ! -f /home/lab-user/.setupcomplete ]; then
  if [ -f /var/lab-user/bashrc.base ]; then
    cp /var/lab-user/bashrc.base /home/lab-user/.bashrc
  fi
  touch /home/lab-user/.setupcomplete
fi

mkdir -p /home/lab-user/homes

exec /usr/bin/tini -- /usr/bin/ttyd \
  -p 7681 \
  -P 5 \
  -t 'theme={"background": "black"}' \
  -W \
  -a \
  /bin/bash /opt/workshop/workshop-shell.sh
