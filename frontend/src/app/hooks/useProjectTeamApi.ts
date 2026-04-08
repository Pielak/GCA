import { useState, useCallback } from 'react';
import axios, { AxiosError } from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

interface ApiError {
  message: string;
  status?: number;
}

interface PendingInvite {
  invite_id: string;
  email: string;
  role: string;
  status: string;
  invited_at: string;
  expires_at: string;
}

interface InviteResponse {
  invite_id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  invite_url: string;
}

interface AcceptInviteResponse {
  project_id: string;
  project_name: string;
  role: string;
  message: string;
  first_access_required: boolean;
}

interface UseProjectTeamApiReturn {
  inviteTeamMember: (
    projectId: string,
    email: string,
    role: string
  ) => Promise<{ success: boolean; data?: InviteResponse; error?: ApiError }>;
  getPendingInvites: (projectId: string) => Promise<{ success: boolean; invites?: PendingInvite[]; error?: ApiError }>;
  acceptInvite: (projectId: string, token: string) => Promise<{ success: boolean; data?: AcceptInviteResponse; error?: ApiError }>;
}

export const useProjectTeamApi = (): UseProjectTeamApiReturn => {
  const getAuthHeader = () => {
    const token = localStorage.getItem('access_token');
    return {
      Authorization: `Bearer ${token}`,
    };
  };

  const inviteTeamMember = useCallback(
    async (projectId: string, email: string, role: string) => {
      try {
        const response = await axios.post(
          `${API_URL}/projects/${projectId}/invite`,
          { email, role },
          { headers: getAuthHeader() }
        );
        return { success: true, data: response.data };
      } catch (error) {
        const axiosError = error as AxiosError<any>;
        return {
          success: false,
          error: {
            message: axiosError.response?.data?.detail || 'Erro ao enviar convite',
            status: axiosError.response?.status,
          },
        };
      }
    },
    []
  );

  const getPendingInvites = useCallback(
    async (projectId: string) => {
      try {
        const response = await axios.get(`${API_URL}/projects/${projectId}/invites`, {
          headers: getAuthHeader(),
        });
        return { success: true, invites: response.data.invites };
      } catch (error) {
        const axiosError = error as AxiosError<any>;
        return {
          success: false,
          error: {
            message: axiosError.response?.data?.detail || 'Erro ao carregar convites',
            status: axiosError.response?.status,
          },
        };
      }
    },
    []
  );

  const acceptInvite = useCallback(
    async (projectId: string, token: string) => {
      try {
        const response = await axios.post(`${API_URL}/projects/${projectId}/accept-invite`, {
          token,
        });
        return { success: true, data: response.data };
      } catch (error) {
        const axiosError = error as AxiosError<any>;
        return {
          success: false,
          error: {
            message: axiosError.response?.data?.detail || 'Erro ao aceitar convite',
            status: axiosError.response?.status,
          },
        };
      }
    },
    []
  );

  return {
    inviteTeamMember,
    getPendingInvites,
    acceptInvite,
  };
};

export default useProjectTeamApi;
