/** Zod schemas — single source of truth for form validation. */
import { z } from "zod";

import { isValidStudentId } from "@/src/utils/diuValidation";

export const profileSchema = z.object({
  name: z
    .string()
    .trim()
    .min(2, "Full name is required")
    .max(80, "Name must be 80 characters or less"),
  student_id: z
    .string()
    .trim()
    .refine(isValidStudentId, {
      message: "Student ID must match xxx-xx-xxx or xxx-xx-xxxx (e.g. 252-35-166).",
    }),
  department: z
    .string()
    .trim()
    .min(1, "Department is required")
    .max(100, "Department is required"),
  batch: z
    .string()
    .trim()
    .min(1, "Batch is required")
    .max(50, "Batch must be 50 characters or less"),
  room_number: z
    .string()
    .trim()
    .max(20, "Room number must be 20 characters or less")
    .optional()
    .or(z.literal("")),
  hostel_name: z
    .string()
    .trim()
    .max(100, "Hostel name must be 100 characters or less")
    .optional()
    .or(z.literal("")),
  phone: z
    .string()
    .trim()
    .max(20, "Phone must be 20 characters or less")
    .optional()
    .or(z.literal("")),
});

export type ProfileFormValues = z.infer<typeof profileSchema>;
