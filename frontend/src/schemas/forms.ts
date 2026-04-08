import { z } from 'zod'

/**
 * Response to Ticket Schema
 * Used in the ticket detail modal to respond to support tickets
 */
export const respondToTicketSchema = z.object({
  message: z
    .string()
    .min(10, 'A resposta deve ter pelo menos 10 caracteres')
    .max(5000, 'A resposta não pode exceder 5000 caracteres'),
  isResolution: z.boolean().default(false),
})

export type RespondToTicketInput = z.infer<typeof respondToTicketSchema>

/**
 * Test Webhook Schema
 * Used in the integrations page to test webhooks
 */
export const testWebhookSchema = z.object({
  integrationType: z.enum(['teams', 'slack', 'discord'], {
    errorMap: () => ({ message: 'Tipo de integração inválido' }),
  }),
  webhookUrl: z
    .string()
    .url('URL inválida')
    .min(10, 'URL muito curta'),
})

export type TestWebhookInput = z.infer<typeof testWebhookSchema>

/**
 * Reset Password Schema
 * Used when resetting user passwords
 */
export const resetPasswordSchema = z.object({
  email: z
    .string()
    .email('Email inválido'),
})

export type ResetPasswordInput = z.infer<typeof resetPasswordSchema>

/**
 * Login Form Schema
 * Used in the login page
 */
export const loginSchema = z.object({
  email: z
    .string()
    .email('Email inválido'),
  password: z
    .string()
    .min(6, 'Senha deve ter pelo menos 6 caracteres'),
})

export type LoginInput = z.infer<typeof loginSchema>
