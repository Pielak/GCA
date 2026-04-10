import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { apiClient } from '@/lib/api'

interface ProjectPermissions {
  role: string
  actions: string[]
  isReadOnly: boolean
}

export function useProjectPermissions() {
  const { id: projectId } = useParams<{ id: string }>()
  const [permissions, setPermissions] = useState<ProjectPermissions>({
    role: '',
    actions: [],
    isReadOnly: true,
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!projectId) return

    const fetchPermissions = async () => {
      try {
        const res = await apiClient.get(`/projects/${projectId}/permissions`)
        setPermissions({
          role: res.data.role,
          actions: res.data.actions,
          isReadOnly: res.data.is_read_only,
        })
      } catch {
        setPermissions({ role: '', actions: [], isReadOnly: true })
      } finally {
        setLoading(false)
      }
    }

    fetchPermissions()
  }, [projectId])

  const can = (action: string): boolean => {
    return permissions.actions.includes(action)
  }

  return {
    can,
    role: permissions.role,
    isReadOnly: permissions.isReadOnly,
    loading,
  }
}
