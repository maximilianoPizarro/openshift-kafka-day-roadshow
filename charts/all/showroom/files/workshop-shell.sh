#!/bin/bash
# One shell per terminal connection. Identity and files stay under that user's home
# so oc login cannot overwrite another participant's kubeconfig.
set -eu

session="${1:-}"
if [[ ! "$session" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$ ]]; then
  session="session-${RANDOM}${RANDOM}"
fi

root="${WORKSHOP_HOME_ROOT:-/home/lab-user/homes}"
home="${root}/${session}"
mkdir -p "${home}/.kube"
chmod 700 "${home}" "${home}/.kube" || true

if [ ! -f "${home}/.kube/config" ]; then
  cat > "${home}/.kube/config" <<'EOF'
apiVersion: v1
kind: Config
clusters: []
contexts: []
current-context: ""
users: []
EOF
  chmod 600 "${home}/.kube/config" || true
fi

if [ ! -f "${home}/.bashrc" ]; then
  if [ -f /var/lab-user/bashrc.base ]; then
    cp /var/lab-user/bashrc.base "${home}/.bashrc"
  elif [ -f /home/lab-user/.bashrc ]; then
    cp /home/lab-user/.bashrc "${home}/.bashrc"
  else
    touch "${home}/.bashrc"
  fi
fi

if ! grep -q 'WORKSHOP_SESSION=' "${home}/.bashrc"; then
  cat >> "${home}/.bashrc" <<EOF

export WORKSHOP_SESSION=$(printf '%q' "$session")
export KUBECONFIG=$(printf '%q' "${home}/.kube/config")
EOF
fi

export HOME="$home"
export KUBECONFIG="${home}/.kube/config"
export WORKSHOP_SESSION="$session"
cd "$home"
exec /usr/bin/bash -i
