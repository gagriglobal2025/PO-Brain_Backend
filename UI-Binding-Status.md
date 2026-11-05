# PO-Brain — UI-to-API Binding & Status Report

This document outlines the current integration status between the **Vite/React Frontend** and the **ASP.NET Core 8 Web API Backend**. It highlights which UI screens have corresponding backend APIs, whether those APIs are complete, and what binding operations are pending.

---

## 1. Executive Summary

*   **Backend API Status:** **100% Complete**  
    All endpoints for authentication, password reset (OTP), dashboard metrics, filtering, CSV export, and notifications are implemented in the C# controllers and database schemas.
*   **Vite/React Frontend Status:** **Screens Designed (Mocked)**  
    All major dashboard and tracking layouts are fully styled and visually complete using Tailwind CSS and shadcn/ui.
*   **Binding Status:** **Pending**  
    Currently, all frontend pages operate on hardcoded mock datasets (`extractionData`, `logData`, `failedTransactions`, etc.). There is no API client or connection layer (`fetch`/`axios`) configured. Binding the frontend to retrieve and modify live data from the backend is the primary outstanding integration task.

---

## 2. UI Screen to API Status Matrix

| UI Screen | Route | UI Layout Status | API Endpoint(s) | API Status | Binding Status | Key Integration Action Required |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Login Screen** | `/login` | ✅ Complete | `POST /api/auth/login` | ✅ Complete | ❌ Pending | Wire submission, save JWT to storage, add Auth Header interceptor. |
| **Forgot / Reset Password** | *(Inside Login)* | ❌ Pending | `POST /api/auth/forgot-password`<br>`POST /api/auth/reset-password` | ✅ Complete | ❌ Pending | Add Modal/Views to enter email for OTP, and to submit OTP + new password. |
| **Dashboard** | `/` | ✅ Complete | `GET /api/dashboard/stats`<br>`GET /api/dashboard/recent-extractions`<br>`GET /api/dashboard/health`<br>`WS /hubs/health` | ✅ Complete | ❌ Pending | Fetch card numbers, recent records, and open SignalR socket for real-time health updates. |
| **Extraction Results** | `/extraction` | ✅ Complete | `GET /api/extractions`<br>`POST /api/extractions/filter`<br>`POST /api/extractions/export` | ✅ Complete | ❌ Pending | Connect table grid to filter query endpoint; add "Export Results" button for CSV download. |
| **Processing Logs** | `/logs` | ✅ Complete | `GET /api/logs`<br>`GET /api/logs/export`<br>`WS /hubs/logs` | ✅ Complete | ❌ Pending | Fetch table rows, bind "Export Logs" button, connect to SignalR stream for live logs. |
| **Failed Transactions** | `/failed` | ✅ Complete | `GET /api/failed-transactions`<br>`POST /api/failed-transactions/filter`<br>`POST /api/failed-transactions/export` | ✅ Complete | ❌ Pending | Bind table to failed transaction records; add "Export Failures" button. |
| **Notification Bell** | *(Header Bar)* | ✅ Complete | `GET /api/notifications/count`<br>`GET /api/notifications`<br>`PUT /api/notifications/{id}/read` | ✅ Complete | ❌ Pending | Query count to display badge; add popover with log items and click-to-read binding. |

---

## 3. Detailed Screen Breakdown & Requirements

### 3.1 Login Screen (`/login`)
*   **Visual Status:** Complete. The right panel has email/password fields, check boxes, and a secure sign-in button. The left panel features a styled banner.
*   **Mock Behavior:** Accepting any credentials logs the user in and navigates to the dashboard via a mock `setTimeout`.
*   **Binding Requirements:**
    1.  Call [AuthController.cs](file:///e:/narayana/PO-Brain/Backend/Controllers/AuthController.cs) `POST /api/auth/login`.
    2.  Store the returned JWT Token (`token`) and user role/profile details in `localStorage` or session cookies.
    3.  Create an Axios/Fetch client wrapper that automatically appends the token in the `Authorization: Bearer <token>` header for all subsequent API requests.
    4.  Redirect to `/` upon success, or display a validation toast on error codes (401/400).

### 3.2 Forgot & Reset Password Modal / Screen
*   **Visual Status:** **Pending**. There is only a dummy text link `Reset Password?` in [Login.tsx](file:///e:/narayana/PO-Brain/Web/PO-Brain/src/pages/Login.tsx#L122-L124) pointing to `#`.
*   **Binding Requirements:**
    1.  Design a sub-screen or popover in React to handle two distinct user flows:
        *   **Step 1:** Enter email address -> triggers `POST /api/auth/forgot-password` to email an OTP reset code.
        *   **Step 2:** Enter email address, the received OTP code, and a new password -> triggers `POST /api/auth/reset-password`.
    2.  Directly bind input states to the authentication API endpoints and navigate the user back to the login view on successful completion.

### 3.3 Dashboard Screen (`/`)
*   **Visual Status:** Complete. Renders 5 summary cards, a recent activities grid, and 24-hour processing progress bars.
*   **Mock Behavior:** Utilizes a hardcoded `stats` list, a mocked `<RecentActivityTable />`, and static `<ProcessingHealth />` bars.
*   **Binding Requirements:**
    1.  Replace the static `stats` array with values queried from [DashboardController.cs](file:///e:/narayana/PO-Brain/Backend/Controllers/DashboardController.cs) `GET /api/dashboard/stats`.
    2.  Query `GET /api/dashboard/recent-extractions?count=10` to dynamically populate the recent extractions grid.
    3.  Load initial bar percentages from `GET /api/dashboard/health`.
    4.  *(Optional but Recommended)*: Connect to the [HealthStreamHub](file:///e:/narayana/PO-Brain/Backend/Hubs/HealthStreamHub.cs) WebSocket endpoint `/hubs/health` via the `@microsoft/signalr` client to update stat counts and health percentages live without refreshing the page.

### 3.4 Extraction Results Screen (`/extraction`)
*   **Visual Status:** Complete. Shows a grid listing PO data, CAS codes, chemical items, delivery details, and status badges, with a top filter/search bar.
*   **Mock Behavior:** Reads from a static `extractionData` array of 4 items.
*   **Binding Requirements:**
    1.  Query [ExtractionsController.cs](file:///e:/narayana/PO-Brain/Backend/Controllers/ExtractionsController.cs) `GET /api/extractions` or `POST /api/extractions/filter` to fetch paginated rows.
    2.  Map search input and filters (from the popover) to the `POST /api/extractions/filter` payload.
    3.  Add an **"Export Results"** action button. Wire it to request a CSV file from `POST /api/extractions/export`, and save the byte blob to the browser filesystem as a `.csv` download.

### 3.5 Processing Logs Screen (`/logs`)
*   **Visual Status:** Complete. Displays running transaction timestamps, logs level badges, sender/subject, messages, and an "Export Logs" button. Includes a green "Connected to Live Log Stream" indicator.
*   **Mock Behavior:** Reads from static `logData` array. The live log stream indicator is visual only.
*   **Binding Requirements:**
    1.  Fetch historical logs on component load by calling [LogsController.cs](file:///e:/narayana/PO-Brain/Backend/Controllers/LogsController.cs) `GET /api/logs`.
    2.  Listen to the SignalR log hub `/hubs/logs` using `@microsoft/signalr` and append new logs as they are pushed in real-time from the backend.
    3.  Bind the "Export Logs" button to request `/api/logs/export` with current level/search queries to download the generated CSV.

### 3.6 Failed Transactions Screen (`/failed`)
*   **Visual Status:** Complete. Renders a grid showing failed orders, quantities, error reasons, and emails.
*   **Mock Behavior:** Displays a static list of 5 failed items.
*   **Binding Requirements:**
    1.  Bind the table rows to data returned by [FailedTransactionsController.cs](file:///e:/narayana/PO-Brain/Backend/Controllers/FailedTransactionsController.cs) `GET /api/failed-transactions` or `POST /api/failed-transactions/filter`.
    2.  Link the query page parameters, filters, and search bar to reload the paginated grid.
    3.  Add an **"Export Failures"** button to request `POST /api/failed-transactions/export` to download a CSV payload of filtered failure logs.

### 3.7 Notification Bell (Top Header Navigation)
*   **Visual Status:** Complete. The header contains a bell icon displaying a hardcoded red `2` badge indicator.
*   **Mock Behavior:** Clicking the bell does not open an alert interface or dismiss count badges.
*   **Binding Requirements:**
    1.  Call [NotificationsController.cs](file:///e:/narayana/PO-Brain/Backend/Controllers/NotificationsController.cs) `GET /api/notifications/count` on mount and set the number inside the red badge.
    2.  Open a popover menu on click to display the list of notifications queried via `GET /api/notifications?unreadOnly=true`.
    3.  Wire "Mark as Read" click actions on individual notifications to invoke `PUT /api/notifications/{notificationId}/read`, decreasing the badge count.
