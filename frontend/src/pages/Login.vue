<template>
  <div class="login-wrap">
    <!-- 左侧品牌区 -->
    <section class="login-left">
      <div class="left-deco">
        <div class="deco-blob deco-blob-1"></div>
        <div class="deco-blob deco-blob-2"></div>
        <div class="deco-grid"></div>
      </div>
      <div class="left-logo">
        <div class="logo-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M3 3h7v7H3V3zm11 0h7v7h-7V3zM3 14h7v7H3v-7zm11 0h7v7h-7v-7z" fill="white" fill-opacity="0.9"/></svg>
        </div>
        <span class="logo-text">Chat-BI</span>
      </div>
      <div class="left-content">
        <h1 class="left-title">用自然语言，<br/>解锁数据洞察</h1>
        <p class="left-desc">Chat-BI 是专为现代企业打造的智能数据中台，通过大语言模型驱动，让非技术人员也能轻松进行深度数据探索与多维分析。</p>
        <div class="left-card">
          <div class="left-card-row">
            <div class="status-dot"></div>
            <span>AI 引擎已就绪</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill"></div>
          </div>
          <span class="progress-label">SYSTEM MONITORING ACTIVE</span>
        </div>
      </div>
      <div class="left-footer">2026 Digital China，all right reserved.
</div>
    </section>

    <!-- 右侧登录区 -->
    <main class="login-right">
      <div class="login-form-wrap">
        <div class="form-header">
          <div class="form-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z" fill="#1fb8cc"/></svg>
          </div>
          <h2>欢迎回来</h2>
          <p>请使用账号密码登录</p>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" class="login-form" @submit.prevent="handleLogin">
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
              size="large"
              placeholder="账号"
              autocomplete="username"
              clearable
            />
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              size="large"
              placeholder="密码"
              autocomplete="current-password"
              show-password
            />
          </el-form-item>
          <el-form-item class="login-submit-item">
            <el-button
              type="primary"
              size="large"
              class="login-btn"
              native-type="submit"
              :loading="loading"
            >
              <span>{{ loading ? '登录中...' : '登录' }}</span>
              <svg v-if="!loading" width="18" height="18" viewBox="0 0 24 24" fill="none" style="margin-left:6px"><path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8-8-8z" fill="white"/></svg>
            </el-button>
          </el-form-item>
        </el-form>

      </div>
    </main>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '@/utils/request'
import { setAuthSession, setCurrentSpaceId } from '@/utils/auth'

const router = useRouter()
const loading = ref(false)
const formRef = ref(null)
const form = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const handleLogin = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    // 调用后端登录API
    const userInfo = await request({
      url: '/users/login',
      method: 'post',
      data: {
        username: form.username.trim(),
        password: form.password
      }
    })

    if (!userInfo) {
      ElMessage.error('登录失败，未返回用户信息')
      return
    }

    // 获取当前用户的空间信息
    let spaceId = 1
    try {
      const spaceInfo = await request({ url: '/spaces/current', method: 'get' })
      if (spaceInfo && spaceInfo.id) {
        spaceId = spaceInfo.id
      }
    } catch (e) {
      console.error('获取当前空间失败', e)
    }

    // 保存会话信息
    setAuthSession({
      token: 'backend_token_' + userInfo.id,
      username: userInfo.username,
      role: userInfo.system_role,
      displayName: userInfo.display_name || userInfo.username,
      userId: userInfo.id,
      system_role: userInfo.system_role
    })

    // 保存当前空间
    setCurrentSpaceId(spaceId)

    ElMessage.success(`欢迎，${userInfo.display_name || userInfo.username}`)
    router.push('/')
  } catch (error) {
    ElMessage.error(error.message || '登录失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  display: flex;
  height: 100vh;
  width: 100%;
  overflow: hidden;
  font-family: 'Inter', 'PingFang SC', sans-serif;
}

/* ===== 左侧 ===== */
.login-left {
  display: none;
  width: 40%;
  background: #0f172a;
  flex-direction: column;
  justify-content: space-between;
  padding: 48px;
  position: relative;
  overflow: hidden;
}

@media (min-width: 768px) {
  .login-left { display: flex; }
  .login-right { width: 60%; }
}

.left-deco { position: absolute; inset: 0; z-index: 0; opacity: 0.2; }
.deco-blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  mix-blend-mode: screen;
}
.deco-blob-1 { top: -10%; left: -10%; width: 60%; height: 60%; background: #1fb8cc; }
.deco-blob-2 { bottom: -10%; right: -10%; width: 50%; height: 50%; background: #575992; }
.deco-grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle at 2px 2px, rgba(255,255,255,0.05) 1px, transparent 0);
  background-size: 32px 32px;
}

.left-logo {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: linear-gradient(135deg, #1fb8cc, #15a5b8);
  display: flex;
  align-items: center;
  justify-content: center;
}
.logo-text { font-size: 22px; font-weight: 700; color: #fff; }

.left-content { position: relative; z-index: 1; margin-bottom: 80px; }
.left-title {
  font-size: 40px;
  font-weight: 700;
  color: #fff;
  line-height: 1.3;
  margin-bottom: 20px;
}
.left-desc { color: #94a3b8; font-size: 16px; line-height: 1.7; max-width: 380px; }

.left-card {
  margin-top: 40px;
  background: rgba(255,255,255,0.03);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.05);
  padding: 20px 24px;
  border-radius: 12px;
  display: inline-flex;
  flex-direction: column;
  gap: 12px;
  max-width: 320px;
}
.left-card-row { display: flex; align-items: center; gap: 10px; }
.status-dot {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: rgba(16,185,129,0.15);
  display: flex; align-items: center; justify-content: center;
}
.status-dot::after {
  content: '';
  width: 10px; height: 10px;
  border-radius: 50%;
  background: #34d399;
}
.left-card-row span { color: #fff; font-size: 14px; font-weight: 500; }
.progress-bar { height: 8px; background: #1e293b; border-radius: 99px; overflow: hidden; }
.progress-fill { height: 100%; width: 66%; background: #1fb8cc; border-radius: 99px; }
.progress-label { font-size: 11px; color: #64748b; letter-spacing: 0.08em; }

.left-footer { position: relative; z-index: 1; color: #475569; font-size: 13px; }

/* ===== 右侧 ===== */
.login-right {
  width: 100%;
  background: #f9f9ff;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
}

.login-form-wrap { width: 100%; max-width: 420px; }

.form-header { text-align: center; margin-bottom: 40px; }
.form-icon {
  display: inline-flex;
  padding: 16px;
  border-radius: 50%;
  background: #e9f8fa;
  margin-bottom: 20px;
}
.form-header h2 { font-size: 24px; font-weight: 700; color: #141b2b; margin-bottom: 8px; }
.form-header p { font-size: 14px; color: #464554; }

.login-form {
  width: 100%;
}

.login-submit-item {
  margin-bottom: 0;
}

.login-submit-item :deep(.el-form-item__content) {
  margin-left: 0 !important;
}

.login-btn {
  width: 100%;
  height: 48px;
  font-size: 15px;
  font-weight: 600;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.form-footer {
  margin-top: 40px;
  padding-top: 24px;
  border-top: 1px solid #e1e8fd;
  text-align: center;
}
.form-footer p { font-size: 14px; color: #464554; }
.form-footer a { color: #1fb8cc; font-weight: 600; text-decoration: none; }
.form-footer a:hover { text-decoration: underline; }
</style>
