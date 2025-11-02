#!/bin/bash
# Deploy Relay AI Beta to Production
# Targets: Railway (API) + Vercel (Web)

set -e

echo "🚀 Relay AI Beta Deployment Script"
echo "=================================="

# Check prerequisites
command -v railway >/dev/null 2>&1 || { echo "❌ Railway CLI not installed. Install: npm i -g @railway/cli"; exit 1; }
command -v vercel >/dev/null 2>&1 || { echo "❌ Vercel CLI not installed. Install: npm i -g vercel"; exit 1; }

# 1. Deploy API to Railway
echo ""
echo "📦 Step 1: Deploy API to Railway"
echo "---------------------------------"

# Create railway.toml if not exists
if [ ! -f railway.toml ]; then
    cat > railway.toml << 'EOF'
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "python -m uvicorn relay_ai.platform.api.mvp:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"

[environments.production]
RELAY_ENV = "production"
EOF
    echo "✓ Created railway.toml"
fi

# Create requirements.txt if not exists
if [ ! -f requirements.txt ]; then
    cat > requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.2
python-jose[cryptography]==3.3.0
asyncpg==0.29.0
httpx==0.25.2
redis==5.0.1
python-multipart==0.0.6
supabase==2.3.0
openai==1.6.0
tiktoken==0.5.2
numpy==1.24.3
EOF
    echo "✓ Created requirements.txt"
fi

echo "Deploying API to Railway..."
echo "Run: railway login"
echo "Then: railway up"
echo ""
echo "After deployment, get your URL:"
echo "railway open"
echo ""

# 2. Deploy Web to Vercel
echo "📦 Step 2: Deploy Web to Vercel"
echo "--------------------------------"

cd relay_ai/product/web

# Create vercel.json if not exists
if [ ! -f vercel.json ]; then
    cat > vercel.json << 'EOF'
{
  "framework": "nextjs",
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "env": {
    "NEXT_PUBLIC_API_URL": "@api_url",
    "NEXT_PUBLIC_APP_URL": "@app_url"
  }
}
EOF
    echo "✓ Created vercel.json"
fi

echo "Deploying Web to Vercel..."
echo "Run: vercel --prod"
echo ""

cd ../../..

# 3. Post-deployment checklist
echo ""
echo "📋 Post-Deployment Checklist"
echo "-----------------------------"
echo ""
echo "[ ] 1. Set environment variables in Railway:"
echo "    railway variables set DATABASE_URL=..."
echo "    railway variables set SUPABASE_URL=..."
echo "    railway variables set SUPABASE_JWT_SECRET=..."
echo "    railway variables set OPENAI_API_KEY=..."
echo ""
echo "[ ] 2. Set environment variables in Vercel:"
echo "    Go to project settings > Environment Variables"
echo "    Add NEXT_PUBLIC_API_URL=https://your-api.railway.app"
echo ""
echo "[ ] 3. Configure Supabase:"
echo "    - Run SQL script: scripts/setup_supabase_beta.sql"
echo "    - Enable Email auth"
echo "    - Create Storage bucket 'user-files'"
echo "    - Add your domains to allowed URLs"
echo ""
echo "[ ] 4. Test the deployment:"
echo "    curl https://your-api.railway.app/health"
echo "    curl https://your-api.railway.app/api/v1/knowledge/health"
echo ""
echo "[ ] 5. Invite beta users:"
echo "    Use scripts/invite_beta_users.py"
echo ""
echo "✅ Deployment script complete!"
