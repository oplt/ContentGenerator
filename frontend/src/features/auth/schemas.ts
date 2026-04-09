import { z } from "zod";

export const signInSchema = z.object({
    email: z.string().email("Enter a valid email"),
    password: z.string().min(1, "Password is required"),
    mfa_code: z
      .string()
      .trim()
      .optional()
      .refine((value) => !value || /^[0-9]{6}$/.test(value), "Enter a valid 6-digit code"),
});

export const forgotPasswordSchema = z.object({
    email: z.string().email("Enter a valid email"),
});

export const signUpSchema = z.object({
    full_name: z.string().optional(),
    email: z.string().email("Enter a valid email"),
    password: z.string().min(8, "Password must be at least 8 characters"),
    admin_invite_code: z.string().optional(),
});

export type SignInValues = z.infer<typeof signInSchema>;
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;
export type SignUpValues = z.infer<typeof signUpSchema>;
