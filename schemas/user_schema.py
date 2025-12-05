from pydantic import BaseModel, EmailStr


# --- 用户数据模型 ---


# 存储在 NiceGUI app.storage.general 中的用户信息模型
class StoredUser(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool = True
    is_superuser: bool = False

    password_hash: str


# --- API 输入模型 ---


# 用户注册
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str  # 在业务逻辑层会被哈希


# 用户登录
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# 用户修改密码
class UserModifyPassword(BaseModel):
    current_password: str
    new_password: str


# --- API 输出模型 ---


# 用户信息
class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool
    is_superuser: bool
