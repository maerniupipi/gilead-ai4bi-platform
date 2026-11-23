<template>
  <Teleport to="body">
    <Transition name="overlay">
      <div v-if="visible" class="space-loading-overlay" @keydown.prevent>
        <!-- 背景装饰粒子 -->
        <div class="bg-particles">
          <span v-for="i in 12" :key="i" class="particle" :style="{ '--d': i }"></span>
        </div>

        <div class="loading-card">
          <!-- 动画图标：四方形阵列 -->
          <div class="icon-array">
            <div class="array-grid">
              <div class="array-cell" v-for="i in 4" :key="i" :style="{ '--i': i }">
                <div class="cell-inner"></div>
              </div>
            </div>
            <div class="icon-ring"></div>
          </div>

          <!-- 文本 -->
          <div class="loading-texts">
            <h3 class="loading-title">正在切换空间</h3>
            <p class="loading-subtitle">Switching workspace...</p>
          </div>

          <!-- 进度条 -->
          <div class="progress-track">
            <div class="progress-fill" ref="progressRef"></div>
          </div>

          <div class="loading-hint">页面即将刷新</div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['complete'])

const progressRef = ref(null)

watch(() => props.visible, async (val) => {
  if (val) {
    await nextTick()
    // 等 transition 入场后再开始进度条动画
    setTimeout(() => {
      if (progressRef.value) {
        progressRef.value.style.transition = 'width 1.6s cubic-bezier(0.22, 1, 0.36, 1)'
        progressRef.value.style.width = '100%'
      }
    }, 300)
    // 1.8s 后通知完成
    setTimeout(() => {
      emit('complete')
    }, 1900)
  }
})
</script>

<style scoped>
/* -----------------------------------------------
   Overlay Transition
   ----------------------------------------------- */
.overlay-enter-active {
  transition: opacity 0.4s ease, backdrop-filter 0.4s ease;
}
.overlay-leave-active {
  transition: opacity 0.35s ease;
}
.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}
.overlay-enter-from {
  backdrop-filter: blur(0px);
}

/* -----------------------------------------------
   Overlay
   ----------------------------------------------- */
.space-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 17, 26, 0.55);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  overflow: hidden;
}

/* -----------------------------------------------
   Background Particles
   ----------------------------------------------- */
.bg-particles {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.particle {
  position: absolute;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: rgba(79, 110, 247, 0.25);
  animation: particleFloat 4s ease-in-out infinite;
  animation-delay: calc(var(--d) * 0.25s);
}

.particle:nth-child(1) { top: 15%; left: 10%; }
.particle:nth-child(2) { top: 25%; left: 80%; }
.particle:nth-child(3) { top: 60%; left: 5%; }
.particle:nth-child(4) { top: 75%; left: 85%; }
.particle:nth-child(5) { top: 40%; left: 92%; }
.particle:nth-child(6) { top: 10%; left: 50%; }
.particle:nth-child(7) { top: 85%; left: 40%; }
.particle:nth-child(8) { top: 50%; left: 15%; }
.particle:nth-child(9) { top: 20%; left: 65%; }
.particle:nth-child(10) { top: 70%; left: 30%; }
.particle:nth-child(11) { top: 90%; left: 70%; }
.particle:nth-child(12) { top: 5%; left: 35%; }

@keyframes particleFloat {
  0%, 100% { transform: translateY(0) scale(1); opacity: 0.25; }
  50% { transform: translateY(-20px) scale(1.5); opacity: 0.6; }
}

/* -----------------------------------------------
   Loading Card
   ----------------------------------------------- */
.loading-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  padding: 48px 56px 40px;
  background: rgba(255, 255, 255, 0.97);
  border-radius: 24px;
  box-shadow:
    0 24px 80px rgba(0, 0, 0, 0.15),
    0 0 0 1px rgba(255, 255, 255, 0.08);
  animation: cardEnter 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes cardEnter {
  from {
    opacity: 0;
    transform: translateY(24px) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* -----------------------------------------------
   Icon Array — 4 squares animation
   ----------------------------------------------- */
.icon-array {
  position: relative;
  width: 72px;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
}

.array-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  width: 44px;
  height: 44px;
  position: relative;
  z-index: 1;
}

.array-cell {
  width: 19px;
  height: 19px;
  border-radius: 4px;
  overflow: hidden;
}

.cell-inner {
  width: 100%;
  height: 100%;
  border-radius: 4px;
  background: #1fb8cc;
  animation: cellPop 1.4s ease-in-out infinite;
  animation-delay: calc(var(--i) * 0.12s);
  transform-origin: center;
}

@keyframes cellPop {
  0%, 100% {
    transform: scale(1);
    opacity: 0.3;
    border-radius: 4px;
  }
  30% {
    transform: scale(1.15);
    opacity: 1;
    border-radius: 3px;
  }
  60% {
    transform: scale(0.95);
    opacity: 0.8;
    border-radius: 3px;
  }
}

/* Ring behind the squares */
.icon-ring {
  position: absolute;
  inset: 0;
  border: 2px solid rgba(79, 110, 247, 0.1);
  border-radius: 50%;
  animation: ringPulse 2s ease-in-out infinite;
}

@keyframes ringPulse {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50% { transform: scale(1.15); opacity: 0; }
}

/* -----------------------------------------------
   Text
   ----------------------------------------------- */
.loading-texts {
  text-align: center;
  margin-bottom: 28px;
}

.loading-title {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 20px;
  font-weight: 600;
  color: #1a1d23;
  margin: 0 0 6px;
  letter-spacing: -0.01em;
}

.loading-subtitle {
  font-size: 13px;
  color: #9ca3af;
  margin: 0;
  font-weight: 400;
}

/* -----------------------------------------------
   Progress Bar
   ----------------------------------------------- */
.progress-track {
  width: 200px;
  height: 3px;
  background: #eef0f5;
  border-radius: 99px;
  overflow: hidden;
  margin-bottom: 16px;
}

.progress-fill {
  width: 0%;
  height: 100%;
  border-radius: 99px;
  background: linear-gradient(90deg, #1fb8cc, #7c5cfc, #1fb8cc);
  background-size: 200% 100%;
  animation: shimmer 1.2s linear infinite;
}

@keyframes shimmer {
  0% { background-position: 0% 0%; }
  100% { background-position: -200% 0%; }
}

.loading-hint {
  font-size: 12px;
  color: #c5c9d4;
  letter-spacing: 0.02em;
}
</style>
