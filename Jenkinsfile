// Equivalent declarative pipeline for Jenkins (evaluated as an alternative in report section 1.5).
pipeline {
  agent any
  environment { IMAGE_TAG = "${env.BRANCH_NAME.replace('/', '-')}-${env.GIT_COMMIT.take(7)}" }
  stages {
    stage('Install')  { steps { sh 'python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt' } }
    stage('Gate')     { steps { sh '. .venv/bin/activate && ./scripts/gate.sh' } }
    stage('Build')    { steps { sh 'docker build --build-arg APP_VERSION=$IMAGE_TAG -t campus-platform:$IMAGE_TAG .' } }
    stage('Deploy staging') {
      when { anyOf { branch 'main'; buildingTag() } }
      environment { CAMPUS_SYNC_TOKEN = credentials('campus-sync-token') }
      steps { sh 'APP_VERSION=$IMAGE_TAG docker compose -f docker-compose.staging.yml up -d && python3 scripts/smoke.py http://localhost:18000 $IMAGE_TAG' }
    }
  }
  post { failure { sh 'docker compose -f docker-compose.staging.yml down -v || true' } }
}
