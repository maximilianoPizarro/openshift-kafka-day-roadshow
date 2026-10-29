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
  # A current context stops oc from falling back to the pod service account,
  # which every terminal would otherwise share until someone logs in.
  cat > "${home}/.kube/config" <<'EOF'
apiVersion: v1
kind: Config
clusters:
- name: workshop
  cluster:
    server: https://127.0.0.1:1
contexts:
- name: workshop
  context:
    cluster: workshop
    user: none
current-context: workshop
users:
- name: none
  user: {}
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
