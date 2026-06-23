/** DIU email and student ID validation — shared by auth forms. */

export function isDiuEmail(email: string): boolean {
  const normalized = email.trim().toLowerCase();
  const parts = normalized.split("@");
  if (parts.length !== 2) return false;
  const domain = parts[1];
  return domain === "diu.edu.bd" || domain.endsWith(".diu.edu.bd");
}

export function isValidStudentId(studentId: string): boolean {
  return /^\d{3}-\d{2}-\d{3,4}$/.test(studentId.trim());
}

/** Strict local-part match applies only to @diu.edu.bd addresses (not department subdomains). */
export function requiresEmailStudentIdMatch(email: string): boolean {
  const normalized = email.trim().toLowerCase();
  const domain = normalized.split("@")[1] ?? "";
  return domain === "diu.edu.bd";
}

export function emailLocalPart(email: string): string {
  return email.trim().toLowerCase().split("@")[0] ?? "";
}
