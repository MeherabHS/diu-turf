/** Zod schema for registration form validation. */
import { z } from "zod";

import { ALLOWED_EMAIL_DOMAIN } from "@/src/constants";

const STUDENT_ID_REGEX = /^\d{3}-\d{2}-\d{3}$/;

export const registerSchema = z
  .object({
    full_name: z
      .string()
      .trim()
      .min(2, "Full name is required")
      .max(80, "Name must be 80 characters or less"),
    email: z
      .string()
      .trim()
      .min(1, "Email is required")
      .email("Enter a valid email")
      .refine((v) => v.toLowerCase().endsWith(ALLOWED_EMAIL_DOMAIN), {
        message: `Email must end with ${ALLOWED_EMAIL_DOMAIN}`,
      }),
    student_id: z
      .string()
      .trim()
      .regex(STUDENT_ID_REGEX, "Student ID must match xxx-xx-xxx (e.g. 252-35-166)"),
    department: z.string().trim().min(1, "Department is required").max(100),
    batch: z.string().trim().min(1, "Batch is required").max(50),
    room_number: z.string().trim().max(20).optional().or(z.literal("")),
    hostel_name: z.string().trim().max(100).optional().or(z.literal("")),
    phone: z.string().trim().max(20).optional().or(z.literal("")),
    password: z.string().min(8, "Password must be at least 8 characters").max(128),
    confirm_password: z.string().min(8, "Confirm your password"),
  })
  .superRefine((data, ctx) => {
    const email = data.email.trim().toLowerCase();
    const studentId = data.student_id.trim();
    const localPart = email.split("@")[0] ?? "";
    if (localPart !== studentId) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Student ID must match the part before @diu.edu.bd.",
        path: ["student_id"],
      });
    }
    if (data.password !== data.confirm_password) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Passwords do not match.",
        path: ["confirm_password"],
      });
    }
  });

export type RegisterFormValues = z.infer<typeof registerSchema>;
