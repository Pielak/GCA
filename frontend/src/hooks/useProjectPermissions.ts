import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { apiClient } from '@/lib/api'

interface ProjectPermissions {
  roles: string[]
  actions: string[]
  isReadOnly: boolean
}

export function useProjectPermissions() {
  const { id: projectId } = useParams<{ id: string }>()
  const [permissions, setPermissions] = useState<ProjectPermissions>({
    roles: [],
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
          roles: res.data.roles || [],
          actions: res.data.actions || [],
          isReadOnly: res.data.is_read_only ?? true,
        })
      } catch {
        setPermissions({ roles: [], actions: [], isReadOnly: true })
      } finally {
        setLoading(false)
      }
    }

    fetchPermissions()
  }, [projectId])

  const can = (action: string): boolean => {
    return permissions.actions.includes(action)
  }

  const hasRole = (role: string): boolean => {
    return permissions.roles.includes(role)
  }

  return {
    can,
    hasRole,
    roles: permissions.roles,
    role: permissions.roles[0] || '',
    isReadOnly: permissions.isReadOnly,
    loading,
  }
}
