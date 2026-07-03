// Loan Advisor E2E — Jenkins Pipeline（与 appium自动化测试_备份.py 业务对齐）
// 工作区可为 loanadvisor_automation 根目录，或上层 pythonProject（自动识别）

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 120, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        booleanParam(name: 'RUN_E2E', defaultValue: true, description: '运行 python run.py 完整 E2E（登录 + KYC + DB 验证）')
        booleanParam(name: 'RUN_PYTEST', defaultValue: false, description: '额外运行 pytest -m e2e')
        booleanParam(name: 'SKIP_PREFLIGHT', defaultValue: false, description: '跳过 adb/Appium 预检（不推荐）')
        string(name: 'DEVICE_NAME_OVERRIDE', defaultValue: '', description: '留空则使用 .env 中的 DEVICE_NAME')
        string(name: 'LOGIN_PHONE_OVERRIDE', defaultValue: '', description: '留空则使用 .env 中的 LOGIN_PHONE')
        string(name: 'PLATFORM_VERSION_OVERRIDE', defaultValue: '', description: '留空则使用 .env 中的 PLATFORM_VERSION')
        string(name: 'APP_PACKAGE_OVERRIDE', defaultValue: '', description: '留空则使用 .env 中的 APP_PACKAGE')
    }

    environment {
        PYTHONIOENCODING = 'UTF-8'
        PYTHONUNBUFFERED = '1'
    }

    stages {
        stage('Init') {
            steps {
                script {
                    if (fileExists('run.py')) {
                        env.PROJECT_DIR = '.'
                    } else if (fileExists('loanadvisor_automation/run.py')) {
                        env.PROJECT_DIR = 'loanadvisor_automation'
                    } else {
                        error('找不到 run.py，请把 Jenkins 工作区指到 loanadvisor_automation 或其上级 pythonProject')
                    }
                    echo "PROJECT_DIR = ${env.PROJECT_DIR}"
                }
            }
        }

        stage('Checkout') {
            when {
                expression { return env.GIT_COMMIT != null }
            }
            steps {
                checkout scm
            }
        }

        stage('Setup Python') {
            steps {
                dir("${env.PROJECT_DIR}") {
                    bat '''
                        python --version
                        if not exist venv\\Scripts\\python.exe (
                            python -m venv venv
                        )
                        call venv\\Scripts\\activate
                        python -m pip install --upgrade pip
                        pip install -r requirements.txt
                        pip install -e .
                        if not exist .env (
                            echo [WARN] 未找到 .env，从 config\\env.example 复制模板
                            copy /Y config\\env.example .env
                        )
                    '''
                }
            }
        }

        stage('Preflight') {
            when {
                expression { return !params.SKIP_PREFLIGHT }
            }
            steps {
                dir("${env.PROJECT_DIR}") {
                    powershell -ExecutionPolicy Bypass -File scripts\\jenkins_preflight.ps1 `
                        -DeviceName "${params.DEVICE_NAME_OVERRIDE}"
                }
            }
        }

        stage('E2E') {
            when {
                expression { return params.RUN_E2E }
            }
            steps {
                dir("${env.PROJECT_DIR}") {
                    script {
                        def extraEnv = []
                        if (params.DEVICE_NAME_OVERRIDE?.trim()) {
                            extraEnv << "DEVICE_NAME=${params.DEVICE_NAME_OVERRIDE.trim()}"
                        }
                        if (params.LOGIN_PHONE_OVERRIDE?.trim()) {
                            extraEnv << "LOGIN_PHONE=${params.LOGIN_PHONE_OVERRIDE.trim()}"
                        }
                        if (params.PLATFORM_VERSION_OVERRIDE?.trim()) {
                            extraEnv << "PLATFORM_VERSION=${params.PLATFORM_VERSION_OVERRIDE.trim()}"
                        }
                        if (params.APP_PACKAGE_OVERRIDE?.trim()) {
                            extraEnv << "APP_PACKAGE=${params.APP_PACKAGE_OVERRIDE.trim()}"
                        }
                        withEnv(extraEnv) {
                            bat '''
                                call venv\\Scripts\\activate
                                set PYTHONPATH=src
                                python run.py
                            '''
                        }
                    }
                }
            }
        }

        stage('Pytest E2E') {
            when {
                expression { return params.RUN_PYTEST }
            }
            steps {
                dir("${env.PROJECT_DIR}") {
                    script {
                        def extraEnv = []
                        if (params.DEVICE_NAME_OVERRIDE?.trim()) {
                            extraEnv << "DEVICE_NAME=${params.DEVICE_NAME_OVERRIDE.trim()}"
                        }
                        if (params.LOGIN_PHONE_OVERRIDE?.trim()) {
                            extraEnv << "LOGIN_PHONE=${params.LOGIN_PHONE_OVERRIDE.trim()}"
                        }
                        withEnv(extraEnv) {
                            bat '''
                                call venv\\Scripts\\activate
                                set PYTHONPATH=src
                                pytest tests -m e2e --alluredir=reports/allure-results -v
                            '''
                        }
                    }
                }
            }
        }

        stage('Allure Report') {
            when {
                expression { return params.RUN_PYTEST || params.RUN_E2E }
            }
            steps {
                dir("${env.PROJECT_DIR}") {
                    bat '''
                        where allure >nul 2>&1
                        if errorlevel 1 (
                            echo [WARN] 未安装 Allure CLI，跳过 HTML 报告生成
                            exit /b 0
                        )
                        if exist reports\\allure-results (
                            allure generate reports/allure-results -o reports/allure-report --clean
                        ) else (
                            echo [WARN] 无 allure-results 目录
                        )
                    '''
                }
            }
        }
    }

    post {
        always {
            script {
                def pd = env.PROJECT_DIR ?: (fileExists('run.py') ? '.' : 'loanadvisor_automation')
                dir(pd) {
                    archiveArtifacts artifacts: 'artifacts/login_result.json', allowEmptyArchive: true
                    archiveArtifacts artifacts: 'reports/**/*.png', allowEmptyArchive: true
                    archiveArtifacts artifacts: 'kyc_*.png', allowEmptyArchive: true
                    archiveArtifacts artifacts: 'after_*.png', allowEmptyArchive: true
                    archiveArtifacts artifacts: 'reports/allure-results/**', allowEmptyArchive: true
                    archiveArtifacts artifacts: 'reports/allure-report/**', allowEmptyArchive: true
                }
            }
        }
        success {
            echo '✅ 构建成功'
        }
        failure {
            echo '❌ 构建失败，请查看 Console Output 与归档截图'
        }
    }
}
