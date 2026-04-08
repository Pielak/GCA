import { useState, useCallback } from 'react';
import axios, { AxiosError } from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

interface ApiError {
  message: string;
  status?: number;
}

interface UseAuthApiReturn {
  requestPasswordReset: (email: string) => Promise<{ success: boolean; error?: ApiError }>;
  verifyResetToken: (token: string) => Promise<{ valid: boolean; message: string; error?: ApiError }>;
  confirmPasswordReset: (token: string, newPassword: string) => Promise<{ success: boolean; error?: ApiError }>;
  changeFirstPassword: (tempPassword: string, newPassword: string) => Promise<{ success: boolean; user?: any; error?: ApiError }>;
}

export const useAuthApi = (): UseAuthApiReturn => {
  const requestPasswordReset = useCallback(
    async (email: string) => {
      try {
        await axios.post(`${API_URL}/auth/reset-password`, { email });
        return { success: true };
      } catch (error) {
        const axiosError = error as AxiosError<any>;
        return {
          success: false,
          error: {
            message: axiosError.response?.data?.detail || 'Erro ao solicitar reset de senha',
            status: axiosError.response?.status,
          },
        };
      }
    },
    []
  );

  const verifyResetToken = useCallback(
    async (token: string) => {
      try {
        const response = await axios.post(`${API_URL}/auth/verify-reset-token`, { token });
        return {
          valid: response.data.valid,
          message: response.data.message,
        };
      } catch (error) {
        const axiosError = error as AxiosError<any>;
        return {
          valid: false,
          message: axiosError.response?.data?.detail || 'Token inválido ou expirado',
          error: {
            message: axiosError.response?.data?.detail || 'Erro ao validar token',
            status: axiosError.response?.status,
          },
        };
      }
    },
    []
  );

  const confirmPasswordReset = useCallback(
    async (token: string, newPassword: string) => {
      try {
        await axios.post(`${API_URL}/auth/reset-password-confirm`, {
          token,
          new_password: newPassword,
        });
        return { success: true };
      } catch (error) {
        const axiosError = error as AxiosError<any>;
        return {
          success: false,
          error: {
            message: axiosError.response?.data?.detail || 'Erro ao confirmar reset de senha',
            status: axiosError.response?.status,
          },
        };
      }
    },
    []
  );

  const changeFirstPassword = useCallback(
    async (tempPassword: string, newPassword: string) => {
      try {
        const token = localStorage.getItem('access_token');
        const response = await axios.post(
          `${API_URL}/auth/change-first-password`,
          {
            temporary_password: tempPassword,
            new_password: newPassword,
          },
          {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }
        );
        return { success: true, user: response.data.user };
      } catch (error) {
        const axiosError = error as AxiosError<any>;
        return {
          success: false,
          error: {
            message: axiosError.response?.data?.detail || 'Erro ao alterar senha',
            status: axiosError.response?.status,
          },
        };
      }
    },
    []
  );

  return {
    requestPasswordReset,
    verifyResetToken,
    confirmPasswordReset,
    changeFirstPassword,
  };
};

export default useAuthApi;
