<template>
  <AutobiLaboratoryContent :project-id="route.params.projectId" @close="goBack" />
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import AutobiLaboratoryContent from '../components/AutobiLaboratoryContent.vue'

const route = useRoute()
const router = useRouter()

function goBack() {
  router.push({ name: 'AutoBIList' })
}
</script>
