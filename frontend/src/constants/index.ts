/** Constants. */
export const ALLOWED_EMAIL_DOMAIN = "@diu.edu.bd";
export const JWT_STORAGE_KEY = "diu.turf.jwt";
export const APP_NAME = "DIU Turf";
export const APP_TAGLINE = "Hostel Turf Booking";
export const ADMIN_CONTACT_EMAIL =
  process.env.EXPO_PUBLIC_ADMIN_CONTACT_EMAIL || "261-35-113@diu.edu.bd";
export const PRIVACY_POLICY_URL =
  process.env.EXPO_PUBLIC_PRIVACY_POLICY_URL || "";
export const TERMS_OF_SERVICE_URL =
  process.env.EXPO_PUBLIC_TERMS_OF_SERVICE_URL || "";
export const ACCOUNT_DELETION_URL =
  process.env.EXPO_PUBLIC_ACCOUNT_DELETION_URL || "";

// User-facing error messages
export const DOMAIN_REJECTED_MESSAGE =
  "Access restricted to Daffodil International University students.";
