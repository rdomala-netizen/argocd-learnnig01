import os
import json
import ssl
from flask import Flask, render_template_string
from urllib.request import Request, urlopen
from urllib.error import URLError

app = Flask(__name__)

# In-cluster K8s API config
K8S_API = "https://kubernetes.default.svc"
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

NAMESPACE = os.environ.get("APP_NAMESPACE", "argocd-learnning01")
DEPLOYMENT_NAME = os.environ.get("DEPLOYMENT_NAME", "gitops-demo")
ARGOCD_APP_NAME = os.environ.get("ARGOCD_APP_NAME", "gitops-demo")
ARGOCD_NAMESPACE = os.environ.get("ARGOCD_NAMESPACE", "argocd")


def k8s_request(path):
    """Make an authenticated request to the K8s API."""
    try:
        with open(TOKEN_PATH, "r") as f:
            token = f.read().strip()

        ctx = ssl.create_default_context(cafile=CA_PATH)
        req = Request(
            f"{K8S_API}{path}",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urlopen(req, context=ctx, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def get_deployment_info():
    """Get deployment replica info from K8s API."""
    data = k8s_request(
        f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{DEPLOYMENT_NAME}"
    )
    if "error" in data:
        return {"desired": "?", "ready": "?", "available": "?", "error": data["error"]}

    spec = data.get("spec", {})
    status = data.get("status", {})
    return {
        "desired": spec.get("replicas", "?"),
        "ready": status.get("readyReplicas", 0),
        "available": status.get("availableReplicas", 0),
        "updated": status.get("updatedReplicas", 0),
        "image": (spec.get("template", {}).get("spec", {})
                  .get("containers", [{}])[0].get("image", "unknown")),
        "strategy": spec.get("strategy", {}).get("type", "unknown"),
        "error": None,
    }


def get_argocd_status():
    """Get ArgoCD application sync status."""
    data = k8s_request(
        f"/apis/argoproj.io/v1alpha1/namespaces/{ARGOCD_NAMESPACE}"
        f"/applications/{ARGOCD_APP_NAME}"
    )
    if "error" in data:
        return {"sync": "Unknown", "health": "Unknown", "error": data["error"]}

    status = data.get("status", {})
    sync = status.get("sync", {})
    health = status.get("health", {})
    op_state = status.get("operationState", {})

    return {
        "sync": sync.get("status", "Unknown"),
        "health": health.get("status", "Unknown"),
        "revision": sync.get("revision", "N/A")[:7],
        "last_sync": op_state.get("finishedAt", "N/A"),
        "message": op_state.get("message", ""),
        "repo": (data.get("spec", {}).get("source", {})
                 .get("repoURL", "Unknown")),
        "error": None,
    }


def get_pods_info():
    """Get pod status for the deployment."""
    data = k8s_request(
        f"/api/v1/namespaces/{NAMESPACE}/pods"
        f"?labelSelector=app={DEPLOYMENT_NAME}"
    )
    if "error" in data:
        return []

    pods = []
    for item in data.get("items", []):
        name = item["metadata"]["name"]
        phase = item["status"].get("phase", "Unknown")
        conditions = item["status"].get("conditions", [])
        ready = any(
            c["type"] == "Ready" and c["status"] == "True"
            for c in conditions
        )
        pods.append({"name": name, "phase": phase, "ready": ready})
    return pods


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="10">
  <title>GitOps Live Dashboard</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Outfit:wght@300;500;700&display=swap');
    :root {
      --bg:#0f1117; --surface:#1a1d27; --border:#2a2d3a;
      --text:#e4e4e7; --muted:#71717a; --accent:#22d3ee;
      --accent-glow:rgba(34,211,238,0.15);
      --green:#4ade80; --orange:#fb923c; --red:#f87171;
    }
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:'Outfit',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
    .grid-bg{
      position:fixed;inset:0;z-index:0;
      background-image:
        linear-gradient(rgba(34,211,238,0.03) 1px,transparent 1px),
        linear-gradient(90deg,rgba(34,211,238,0.03) 1px,transparent 1px);
      background-size:60px 60px;
    }
    .container{position:relative;z-index:1;max-width:960px;margin:0 auto;padding:3rem 2rem}
    header{text-align:center;margin-bottom:2.5rem}
    .logo{
      display:inline-flex;align-items:center;gap:0.75rem;
      font-family:'JetBrains Mono',monospace;font-size:0.8rem;
      color:var(--accent);letter-spacing:0.15em;text-transform:uppercase;margin-bottom:1rem;
    }
    .dot{
      width:8px;height:8px;border-radius:50%;
      box-shadow:0 0 12px;animation:pulse 2s ease-in-out infinite;
    }
    .dot.green{background:var(--green);color:var(--green)}
    .dot.orange{background:var(--orange);color:var(--orange)}
    .dot.red{background:var(--red);color:var(--red)}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
    h1{
      font-size:2.5rem;font-weight:700;
      background:linear-gradient(135deg,var(--text),var(--accent));
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:0.5rem;
    }
    .subtitle{color:var(--muted);font-size:1rem;font-weight:300}
    .live-badge{
      display:inline-flex;align-items:center;gap:0.4rem;
      font-family:'JetBrains Mono',monospace;font-size:0.7rem;
      color:var(--green);margin-top:0.75rem;letter-spacing:0.08em;
    }
    .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.25rem;margin-bottom:2rem}
    .card{
      background:var(--surface);border:1px solid var(--border);
      border-radius:12px;padding:1.5rem;transition:border-color 0.3s,box-shadow 0.3s;
    }
    .card:hover{border-color:var(--accent);box-shadow:0 0 30px var(--accent-glow)}
    .card-label{
      font-family:'JetBrains Mono',monospace;font-size:0.7rem;color:var(--muted);
      text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.5rem;
    }
    .card-value{font-size:1.4rem;font-weight:700}
    .card-detail{font-size:0.8rem;color:var(--muted);margin-top:0.25rem}
    .synced{color:var(--green)} .outofsync{color:var(--orange)} .unknown{color:var(--muted)}
    .healthy{color:var(--green)} .degraded{color:var(--orange)} .missing{color:var(--red)}
    .panel{
      background:var(--surface);border:1px solid var(--border);
      border-radius:12px;padding:1.75rem;margin-bottom:1.25rem;
    }
    .panel h2{
      font-size:1rem;font-weight:500;margin-bottom:1rem;
      display:flex;align-items:center;gap:0.5rem;
    }
    .panel h2::before{content:'';display:block;width:3px;height:16px;background:var(--accent);border-radius:2px}
    .env-table{width:100%;border-collapse:collapse;font-family:'JetBrains Mono',monospace;font-size:0.8rem}
    .env-table tr{border-bottom:1px solid var(--border)}
    .env-table tr:last-child{border-bottom:none}
    .env-table td{padding:0.6rem 0}
    .env-table td:first-child{color:var(--muted);width:40%}
    .pods-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:0.75rem}
    .pod{
      display:flex;align-items:center;gap:0.75rem;
      padding:0.75rem 1rem;border-radius:8px;
      background:rgba(255,255,255,0.02);border:1px solid var(--border);
      font-family:'JetBrains Mono',monospace;font-size:0.78rem;
    }
    .pod-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
    .pod-dot.running{background:var(--green);box-shadow:0 0 8px var(--green)}
    .pod-dot.pending{background:var(--orange);box-shadow:0 0 8px var(--orange)}
    .pod-dot.failed{background:var(--red);box-shadow:0 0 8px var(--red)}
    .pod-name{color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .pod-status{color:var(--muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em}
    footer{text-align:center;color:var(--muted);font-size:0.75rem;padding:2rem 0;border-top:1px solid var(--border)}
    .error-hint{color:var(--orange);font-size:0.8rem;margin-top:0.5rem;font-family:'JetBrains Mono',monospace}
  </style>
</head>
<body>
  <div class="grid-bg"></div>
  <div class="container">
    <header>
      <div class="logo">
        <div class="dot {% if argo.sync == 'Synced' %}green{% elif argo.sync == 'OutOfSync' %}orange{% else %}red{% endif %}"></div>
        argocd · live dashboard
      </div>
      <h1>GitOps Live Dashboard</h1>
      <p class="subtitle">Auto-refreshes every 10 seconds — all data pulled live from the cluster.</p>
      <div class="live-badge"><span class="dot green" style="width:5px;height:5px"></span> LIVE</div>
    </header>

    <div class="cards">
      <div class="card">
        <div class="card-label">Sync Status</div>
        <div class="card-value {% if argo.sync == 'Synced' %}synced{% elif argo.sync == 'OutOfSync' %}outofsync{% else %}unknown{% endif %}">
          {{ argo.sync }}
          {% if argo.sync == 'Synced' %}✓{% elif argo.sync == 'OutOfSync' %}⚠{% endif %}
        </div>
        <div class="card-detail">ArgoCD sync state</div>
      </div>
      <div class="card">
        <div class="card-label">Health</div>
        <div class="card-value {% if argo.health == 'Healthy' %}healthy{% elif argo.health == 'Degraded' %}degraded{% else %}missing{% endif %}">
          {{ argo.health }}
        </div>
        <div class="card-detail">Application health</div>
      </div>
      <div class="card">
        <div class="card-label">Desired Replicas</div>
        <div class="card-value" style="color:var(--accent)">{{ deploy.desired }}</div>
        <div class="card-detail">From deployment spec</div>
      </div>
      <div class="card">
        <div class="card-label">Ready Replicas</div>
        <div class="card-value {% if deploy.ready == deploy.desired %}synced{% else %}outofsync{% endif %}">
          {{ deploy.ready }} / {{ deploy.desired }}
        </div>
        <div class="card-detail">Running &amp; healthy</div>
      </div>
    </div>

    <div class="panel">
      <h2>Pod Status</h2>
      {% if pods %}
      <div class="pods-grid">
        {% for pod in pods %}
        <div class="pod">
          <div class="pod-dot {% if pod.phase == 'Running' and pod.ready %}running{% elif pod.phase == 'Pending' %}pending{% else %}failed{% endif %}"></div>
          <span class="pod-name">{{ pod.name }}</span>
          <span class="pod-status">{{ pod.phase }}</span>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <p style="color:var(--muted);font-size:0.85rem">No pods found.</p>
      {% endif %}
    </div>

    <div class="panel">
      <h2>Deployment Info</h2>
      <table class="env-table">
        <tr><td>Namespace</td><td>{{ namespace }}</td></tr>
        <tr><td>Image</td><td>{{ deploy.image }}</td></tr>
        <tr><td>Strategy</td><td>{{ deploy.strategy }}</td></tr>
        <tr><td>Git Revision</td><td>{{ argo.revision }}</td></tr>
        <tr><td>Last Synced</td><td>{{ argo.last_sync }}</td></tr>
        <tr><td>Repo</td><td style="word-break:break-all">{{ argo.repo }}</td></tr>
      </table>
      {% if deploy.error %}
      <div class="error-hint">⚠ K8s API: {{ deploy.error }}</div>
      {% endif %}
      {% if argo.error %}
      <div class="error-hint">⚠ ArgoCD API: {{ argo.error }}</div>
      {% endif %}
    </div>

    <footer>
      GitOps Live Dashboard · Auto-refreshes every 10s · Powered by K8s &amp; ArgoCD APIs
    </footer>
  </div>
</body>
</html>
"""


@app.route("/")
def dashboard():
    deploy = get_deployment_info()
    argo = get_argocd_status()
    pods = get_pods_info()
    return render_template_string(
        HTML_TEMPLATE,
        deploy=deploy,
        argo=argo,
        pods=pods,
        namespace=NAMESPACE,
    )


@app.route("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
