from fastapi import APIRouter, Depends, HTTPException, status
from ..domain.auth import LoginRequest, LoginResponse


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """
    用户登录接口
    
    - 验证邮箱格式（EmailStr 自动验证）
    - 验证密码强度（最少8位，包含字母和数字）
    """
    # TODO: 实际登录逻辑（查询数据库验证用户凭据）
    # 这里仅返回成功响应用于测试
    return LoginResponse(
        success=True,
        message="登录成功",
        user_data={
            "email": body.email,
            "login_time": "2024-07-04T12:00:00Z"
        }
    )


@router.get("/health")
async def health_check():
    """认证服务健康检查"""
    return {"status": "healthy", "service": "auth"}
