#!/bin/bash

# MaiMBot 双后端一键启动脚本
# 启动配置器后端和回复后端

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查依赖
check_dependencies() {
    log_info "检查依赖..."

    # 检查Python
    if ! command -v python &> /dev/null; then
        log_error "Python 未安装"
        exit 1
    fi

    # 检查conda环境
    if [[ "$CONDA_DEFAULT_ENV" != "maibot" ]]; then
        log_warning "当前不在 maibot conda 环境中"
        log_info "尝试激活 maibot 环境..."

        if command -v conda &> /dev/null; then
            source $(conda info --base)/etc/profile.d/conda.sh
            conda activate maibot 2>/dev/null || {
                log_error "无法激活 maibot conda 环境"
                exit 1
            }
            log_success "已激活 maibot 环境"
        else
            log_error "Conda 未安装"
            exit 1
        fi
    fi

    log_success "依赖检查完成"
}

# 检查端口占用
check_ports() {
    log_info "检查端口占用..."

    # 检查配置器后端端口 (8000)
    if lsof -i :8000 &> /dev/null; then
        log_warning "端口 8000 已被占用"
        read -p "是否要停止占用端口的进程? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            lsof -ti :8000 | xargs kill -9
            log_info "已停止占用端口 8000 的进程"
        else
            log_error "端口 8000 被占用，无法启动配置器后端"
            exit 1
        fi
    fi

    # 检查回复后端端口 (8095)
    if lsof -i :8095 &> /dev/null; then
        log_warning "端口 8095 已被占用"
        read -p "是否要停止占用端口的进程? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            lsof -ti :8095 | xargs kill -9
            log_info "已停止占用端口 8095 的进程"
        else
            log_error "端口 8095 被占用，无法启动回复后端"
            exit 1
        fi
    fi

    log_success "端口检查完成"
}

# 启动配置器后端
start_config_backend() {
    log_info "启动配置器后端..."

    # 创建日志目录
    mkdir -p logs

    # 启动配置器后端
    nohup python -m src.api.main > logs/config_backend.log 2>&1 &
    CONFIG_PID=$!
    echo $CONFIG_PID > .config_backend.pid

    # 等待服务启动
    log_info "等待配置器后端启动..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
            log_success "配置器后端启动成功 (PID: $CONFIG_PID)"
            return 0
        fi
        sleep 1
        echo -n "."
    done

    log_error "配置器后端启动超时"
    return 1
}

# 启动回复后端
start_reply_backend() {
    log_info "启动回复后端..."

    # 启动回复后端
    nohup python bot.py > logs/reply_backend.log 2>&1 &
    REPLY_PID=$!
    echo $REPLY_PID > .reply_backend.pid

    # 等待服务启动
    log_info "等待回复后端启动..."
    for i in {1..60}; do
        if nc -z localhost 8095 2>/dev/null; then
            log_success "回复后端启动成功 (PID: $REPLY_PID)"
            return 0
        fi
        sleep 1
        echo -n "."
    done

    log_error "回复后端启动超时"
    return 1
}

# 显示服务状态
show_status() {
    echo
    echo "=================================="
    echo "MaiMBot 服务状态"
    echo "=================================="

    # 配置器后端状态
    if [[ -f .config_backend.pid ]]; then
        CONFIG_PID=$(cat .config_backend.pid)
        if ps -p $CONFIG_PID > /dev/null 2>&1; then
            echo -e "配置器后端: ${GREEN}运行中${NC} (PID: $CONFIG_PID)"
            echo "  API地址: http://localhost:8000"
            echo "  API文档: http://localhost:8000/docs"
        else
            echo -e "配置器后端: ${RED}未运行${NC}"
            rm -f .config_backend.pid
        fi
    else
        echo -e "配置器后端: ${RED}未启动${NC}"
    fi

    # 回复后端状态
    if [[ -f .reply_backend.pid ]]; then
        REPLY_PID=$(cat .reply_backend.pid)
        if ps -p $REPLY_PID > /dev/null 2>&1; then
            echo -e "回复后端: ${GREEN}运行中${NC} (PID: $REPLY_PID)"
            echo "  WebSocket: ws://localhost:8095/ws"
        else
            echo -e "回复后端: ${RED}未运行${NC}"
            rm -f .reply_backend.pid
        fi
    else
        echo -e "回复后端: ${RED}未启动${NC}"
    fi

    echo "=================================="
    echo "日志文件位置:"
    echo "  配置器后端: logs/config_backend.log"
    echo "  回复后端: logs/reply_backend.log"
    echo "=================================="
}

# 停止服务
stop_servers() {
    log_info "停止所有服务..."

    # 停止配置器后端
    if [[ -f .config_backend.pid ]]; then
        CONFIG_PID=$(cat .config_backend.pid)
        if ps -p $CONFIG_PID > /dev/null 2>&1; then
            kill $CONFIG_PID
            log_info "已停止配置器后端 (PID: $CONFIG_PID)"
        fi
        rm -f .config_backend.pid
    fi

    # 停止回复后端
    if [[ -f .reply_backend.pid ]]; then
        REPLY_PID=$(cat .reply_backend.pid)
        if ps -p $REPLY_PID > /dev/null 2>&1; then
            kill $REPLY_PID
            log_info "已停止回复后端 (PID: $REPLY_PID)"
        fi
        rm -f .reply_backend.pid
    fi

    log_success "所有服务已停止"
}

# 重启服务
restart_servers() {
    log_info "重启服务..."
    stop_servers
    sleep 2
    start_servers
}

# 启动服务
start_servers() {
    log_info "启动 MaiMBot 双后端服务..."

    # 检查依赖和端口
    check_dependencies
    check_ports

    # 创建必要目录
    mkdir -p logs data

    # 启动服务
    if start_config_backend && start_reply_backend; then
        log_success "所有服务启动成功!"
        show_status
        echo
        log_info "使用 'bash $0 status' 查看服务状态"
        log_info "使用 'bash $0 stop' 停止服务"
        log_info "使用 'bash $0 restart' 重启服务"
        log_info "使用 'bash $0 test' 运行集成测试"
        echo
    else
        log_error "服务启动失败"
        stop_servers
        exit 1
    fi
}

# 运行集成测试
run_integration_test() {
    log_info "运行集成测试..."

    # 检查服务是否运行
    if ! curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        log_error "配置器后端未运行，请先启动服务"
        exit 1
    fi

    if ! nc -z localhost 8095 2>/dev/null; then
        log_error "回复后端未运行，请先启动服务"
        exit 1
    fi

    # 运行测试
    python integration_tests/test_runner.py --users 3 --agents 2
}

# 显示帮助信息
show_help() {
    echo "MaiMBot 双后端管理脚本"
    echo
    echo "用法: $0 [命令]"
    echo
    echo "命令:"
    echo "  start     启动配置器后端和回复后端 (默认)"
    echo "  stop      停止所有服务"
    echo "  restart   重启所有服务"
    echo "  status    显示服务状态"
    echo "  test      运行集成测试"
    echo "  help      显示此帮助信息"
    echo
    echo "示例:"
    echo "  $0                # 启动服务"
    echo "  $0 start          # 启动服务"
    echo "  $0 stop           # 停止服务"
    echo "  $0 restart        # 重启服务"
    echo "  $0 status         # 查看状态"
    echo "  $0 test           # 运行测试"
    echo
}

# 主逻辑
main() {
    # 进入项目目录
    cd "$(dirname "$0")/.."

    # 解析命令行参数
    case "${1:-start}" in
        start)
            start_servers
            ;;
        stop)
            stop_servers
            ;;
        restart)
            restart_servers
            ;;
        status)
            show_status
            ;;
        test)
            run_integration_test
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 捕获退出信号
trap 'echo -e "\n${YELLOW}收到中断信号，正在清理...${NC}"; stop_servers; exit 130' INT TERM

# 执行主逻辑
main "$@"