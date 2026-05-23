# Dynamic GitOps Dashboard — Setup Guide

## What This Does

Instead of static HTML, this app runs a small Python (Flask) server **inside the cluster** that queries the Kubernetes and ArgoCD APIs in real-time. The dashboard auto-refreshes every 10 seconds and shows:

- **Live sync status** from ArgoCD (Synced / OutOfSync)
- **Real replica counts** (desired vs ready)
- **Individual pod status** with health indicators
- **Git revision**, last sync time, and deployment info

---

## How It Works

The app uses the Kubernetes **in-cluster API** via the mounted service account token at `/var/run/secrets/kubernetes.io/serviceaccount/token`. The RBAC manifests grant it read-only access to deployments, pods, and ArgoCD Application CRDs.

---

## Setup Steps

### Step 1 — Build the Docker image inside Minikube

Since we're using a custom image, we build it directly in Minikube's Docker daemon so no registry is needed:

```bash
# Point your shell's Docker to Minikube's Docker
eval $(minikube docker-env)

# Build the image (run this from the 'app' folder)
cd app
docker build -t gitops-dashboard:latest .
cd ..
```

The deployment uses `imagePullPolicy: Never`, so Kubernetes will use this local image.

### Step 2 — Delete the old ArgoCD application (if exists)

```bash
kubectl delete application  -n argocd --ignore-not-found
```

### Step 3 — Push the new k8s manifests to your Git repo

Replace the contents of your `argocd-learnnig01` repo with the new `k8s/` folder:

```bash
# Go to your repo directory
cd ~/argocd-learnnig01

# Remove old files (keep .git)
rm -f *.yaml

# If you previously had files at root, restructure into k8s/
mkdir -p k8s
cp /path/to/argocd-dynamic/k8s/* k8s/

# Push
git add .
git commit -m "feat: dynamic live dashboard with K8s API"
git push origin main
```

If your repo has manifests at the root (no `k8s/` folder), either:
- Move them into `k8s/` as shown above, OR
- Change `path: k8s` to `path: .` in `argocd-application.yaml`

### Step 4 — Apply the ArgoCD application

```bash
kubectl apply -f argocd-application.yaml
```

### Step 5 — Access the dashboard

```bash
minikube service  -n argocd-learnning01
```

---

## Testing the Live Updates

### Test 1: Scale replicas via Git

Edit `k8s/deployment.yaml`, change `replicas: 2` to `replicas: 5`:

```bash
# In your repo
sed -i 's/replicas: 2/replicas: 5/' k8s/deployment.yaml
git add . && git commit -m "scale to 5 replicas" && git push origin main
```

Watch the dashboard — within a few minutes, the replica count will update from 2 to 5, and new pods will appear in the pod status section.

### Test 2: Manually scale (creates OutOfSync)

```bash
kubectl scale deployment  -n argocd-learnning01 --replicas=3
```

The dashboard will briefly show 3 replicas and "OutOfSync" status. Then ArgoCD's self-heal will revert it back to what Git says (2 or 5), and the dashboard updates again.

### Test 3: Force sync

```bash
argocd app sync 
```

---

## Rebuilding After Code Changes

If you modify `app.py` and want to update the running app:

```bash
eval $(minikube docker-env)
cd app
docker build -t gitops-dashboard:latest .

# Restart the pods to pick up the new image
kubectl rollout restart deployment  -n argocd-learnning01
```

---

## File Structure

```
argocd-dynamic/
├── app/
│   ├── app.py              ← Flask app (queries K8s + ArgoCD APIs)
│   ├── Dockerfile
│   └── requirements.txt
├── k8s/
│   ├── namespace.yaml
│   ├── rbac.yaml           ← ServiceAccount + ClusterRole (read-only)
│   ├── deployment.yaml     ← Uses gitops-dashboard:latest image
│   └── service.yaml
├── argocd-application.yaml ← Apply this to your cluster (don't push to Git)
└── SETUP.md                ← This file
```
