# PO-Brain — Backend API Endpoints & Specification

This document provides a comprehensive guide to the **ASP.NET Core 8 Web API** endpoints, request/response structures, authorization policies, real-time SignalR streams, and integration interfaces in the PO-Brain system.

---

## 1. Global API Configuration

*   **API Base URL:**
    *   *Local:* `http://localhost:5000` or `https://localhost:5001` (dev server dependent)
    *   *Server Sub-path:* `/coreapiv1pob/` (Reverse-proxied under IIS/Nginx, e.g., `https://hymasynthesis.com/coreapiv1pob/`)
*   **Database Source:** SQL Server database (`hyma_testdb`)
*   **Documentation Playground (Swagger):** 
    *   *Local URL:* `http://localhost:5000/swagger`
    *   *Server URL:* `https://hymasynthesis.com/coreapiv1pob/swagger/index.html` (resolves relative to page base)
*   **CORS Configuration:** Active policy (`AllowFrontend`) whitelists browser requests, exposing headers: `Content-Disposition`, `Content-Type`, and `Content-Length` (necessary for dynamic CSV downloads).

---

## 2. Authentication & Authorization (JWT)

All endpoints, except where explicitly marked as `[AllowAnonymous]`, require a JSON Web Token (JWT) in the request header.

*   **Header Format:** 
    ```http
    Authorization: Bearer <your_jwt_token>
    ```
    *Note: The backend parser is flexible and accepts the token directly with or without the `"Bearer "` prefix.*
*   **Token Validity:** 480 minutes (8 hours).
*   **Claims Injected:**
    *   `ClaimTypes.NameIdentifier` (User ID)
    *   `ClaimTypes.Name` (Username)
    *   `ClaimTypes.Email` (Email)
    *   `full_name` (Full Name)
    *   `ClaimTypes.Role` (Role, e.g., `admin`, `user`)

---

## 3. SignalR WebSockets (Real-Time Streams)

Real-time hubs are authenticated. To authorize a websocket connection, pass the JWT token as a query string parameter: `?access_token=<token>`.

### 3.1 Health Stream Hub
*   **Endpoint Route:** `/hubs/health`
*   **Group Subscriptions:**
    *   Auto-joins group `"health-subscribers"` on connection.
*   **Broadcast Frequency:** Every 30 seconds / 30 minutes.
*   **Data Payload Broadcasted:** Real-time system health metrics:
    ```json
    {
      "pipelineSuccessRate": 95.7,
      "averageProcessingSpeedMs": 1245,
      "uptimePercentage": 100.0,
      "lastCheckedAt": "2026-06-09T11:15:00Z"
    }
    ```

### 3.2 Log & Notification Stream Hub
*   **Endpoint Route:** `/hubs/logs`
*   **Group Subscriptions:**
    *   Auto-joins global group `"log-subscribers"` (streams running pipeline logs).
    *   Auto-joins user-specific group `"user-{userId}"` (streams direct alerts/notifications).
*   **Data Broadcasted:** Streamed `pobrain_processing_logs` lines and immediate popup alerts.

---

## 4. HTTP Endpoints Specification

### 4.1 Authentication Controller (`api/auth`)

Handles credentials validation, session tokens, registration updates, and OTP password-reset flows.

| Method | Sub-route | Auth Policy | Description |
| :--- | :--- | :--- | :--- |
| **POST** | `/login` | `AllowAnonymous` | Authenticates credentials and returns a JWT token. |
| **POST** | `/logout` | `Authorize` | Confirms session termination. |
| **POST** | `/forgot-password` | `AllowAnonymous` | Dispatches an OTP reset code via configured SMTP. |
| **POST** | `/reset-password` | `AllowAnonymous` | Consumes OTP and sets the new password. |
| **GET** | `/me` | `Authorize` | Extracts and decodes claims belonging to current caller. |
| **PUT** | `/update/{userId}` | `Authorize` | Modifies user data (Gated: user can edit self; admins can edit anyone). |
| **DELETE** | `/delete/{userId}` | `Authorize` | Purges a user account (Gated: Admin only). |

#### Payload Examples (`api/auth`):

*   **POST `/login`**
    *   *Request:*
        ```json
        {
          "username": "admin",
          "password": "Password123"
        }
        ```
    *   *Response (200 OK):*
        ```json
        {
          "success": true,
          "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
          "expiration": "2026-06-09T19:15:00Z",
          "user": {
            "id": 1,
            "username": "admin",
            "email": "admin@company.com",
            "fullName": "Administrator",
            "role": "admin"
          }
        }
        ```

*   **POST `/forgot-password`**
    *   *Request:*
        ```json
        {
          "email": "user@company.com"
        }
        ```

*   **POST `/reset-password`**
    *   *Request:*
        ```json
        {
          "email": "user@company.com",
          "token": "649312",
          "newPassword": "SecureNewPassword99!"
        }
        ```

---

### 4.2 Dashboard Controller (`api/dashboard`)

Provides statistical cards, historical success charts, and lists of recent extractions.

| Method | Sub-route | Auth Policy | Description |
| :--- | :--- | :--- | :--- |
| **GET** | `/stats` | `Authorize` | Aggregates summary cards (total orders, processed, failed, pending). |
| **GET** | `/recent-extractions`| `Authorize` | Returns the N most recent extracted POs (clamped `1-50`, defaults to `10`). |
| **GET** | `/health` | `Authorize` | Returns the current pipeline health percentage and error frequencies. |

#### Response Examples (`api/dashboard`):

*   **GET `/stats`**
    *   *Response (200 OK):*
        ```json
        {
          "totalEmails": 4320,
          "processedEmails": 4120,
          "failedEmails": 150,
          "pendingEmails": 50,
          "totalPurchaseOrders": 3850,
          "totalExtractionJobs": 4200
        }
        ```

---

### 4.3 Extractions Controller (`api/extractions`)

Queries successfully parsed PO Headers and child Line Items with filtering and Excel/CSV exporting.

| Method | Sub-route | Auth Policy | Description |
| :--- | :--- | :--- | :--- |
| **GET** | `/` | `Authorize` | Returns a flat, paginated list of purchase orders. Supports `search` query. |
| **POST** | `/filter` | `Authorize` | Fetches purchase orders applying advanced multi-column filters. |
| **POST** | `/export` | `Authorize` | Generates a downloadable CSV containing PO records matching filter constraints. |

#### Request/Response Examples (`api/extractions`):

*   **POST `/filter`**
    *   *Request:*
        ```json
        {
          "search": "CAPLIN",
          "status": "Completed",
          "fromDate": "2026-06-01T00:00:00Z",
          "toDate": "2026-06-09T23:59:59Z",
          "minAmount": 5000.00,
          "maxAmount": 100000.00,
          "page": 1,
          "pageSize": 25
        }
        ```
    *   *Response (200 OK):*
        ```json
        {
          "items": [
            {
              "poId": 1284,
              "poNumber": "PO-2026-8843",
              "poDate": "2026-06-04",
              "vendorName": "Caplin Point Labs Ltd",
              "totalAmount": 12450.00,
              "status": "Completed",
              "lineItemCount": 3,
              "createdAt": "2026-06-04T10:14:22Z"
            }
          ],
          "totalCount": 1,
          "page": 1,
          "pageSize": 25
        }
        ```

*   **POST `/export`**
    *   *Request:* Same JSON filter payload as `/filter`.
    *   *Response (200 OK):* Returns raw string with `Content-Type: text/csv` and header:
        `Content-Disposition: attachment; filename="extractions-2026-06-09-125400.csv"`.

---

### 4.4 Failed Transactions Controller (`api/failed-transactions`)

Monitors POs that could not be mapped or generated structural parser failures (powers the "Failed Transactions" interface).

| Method | Sub-route | Auth Policy | Description |
| :--- | :--- | :--- | :--- |
| **GET** | `/` | `Authorize` | Paginated search list of failure records. |
| **POST** | `/filter` | `Authorize` | Returns filtered items with error logs. |
| **POST** | `/export` | `Authorize` | Generates a downloadable CSV of filtered failure items. |

#### Request/Response Examples (`api/failed-transactions`):

*   **POST `/filter`**
    *   *Request:*
        ```json
        {
          "search": "unknown vendor",
          "errorCategory": "AI_PARSING_FAILED",
          "fromDate": "2026-06-01",
          "toDate": "2026-06-09",
          "page": 1,
          "pageSize": 20
        }
        ```
    *   *Response (200 OK):*
        ```json
        {
          "items": [
            {
              "failedTransactionId": 98,
              "emailId": 412,
              "poNumber": "UNKNOWN",
              "emailFrom": "spammer@unrelated.net",
              "errorReason": "No PO number could be identified in the text body.",
              "failedAt": "2026-06-08T18:02:11Z"
            }
          ],
          "totalCount": 1
        }
        ```

---

### 4.5 Pipeline Logs Controller (`api/logs`)

Exposes real-time event logs inserted by the Python Ingestion Pipeline (`pobrain_processing_logs`).

| Method | Sub-route | Auth Policy | Description |
| :--- | :--- | :--- | :--- |
| **GET** | `/` | `Authorize` | Fetches database logs. Filterable by `level` (DEBUG, INFO, WARN, ERROR) and `search`. |
| **GET** | `/export` | `Authorize` | Generates a downloadable CSV mapping all logs matching criteria. |

*   **GET `/export?level=ERROR&search=IMAP`**
    *   *Response:* Returns file download payload matching the SQL query results.

---

### 4.6 Notifications Controller (`api/notifications`)

Used by the UI to list and dismiss push notifications and banner alerts.

| Method | Sub-route | Auth Policy | Description |
| :--- | :--- | :--- | :--- |
| **GET** | `/count` | `Authorize` | Returns the integer count of unread notifications for the caller. |
| **GET** | `/` | `Authorize` | Paginated list of notifications (`unreadOnly = true/false`). |
| **GET** | `/{notificationId}`| `Authorize` | Details of a specific alert record. |
| **POST** | `/` | `Authorize` | Spawns a custom system-wide notification (Gated: Admin only). |
| **PUT** | `/{notificationId}/read`| `Authorize` | Marks a single notification as read by the user. |
| **PUT** | `/read-all` | `Authorize` | Marks all notifications as read for the user. |
| **DELETE**| `/{notificationId}`| `Authorize` | Purges/removes the notification from the user's view. |

---

### 4.7 Standard System Health Checks (`/health`)

Exposes API container/system health metrics for platform orchestrators (e.g. Kubernetes, AWS ECS, or IIS AppPool).

| Method | Route | Auth Policy | Description |
| :--- | :--- | :--- | :--- |
| **GET** | `/health` | `AllowAnonymous` | Verifies database EF Core connection readiness. |

*   **Response (200 OK - Healthy):**
    ```json
    {
      "status": "Healthy",
      "results": {
        "DbContextCheck": {
          "status": "Healthy",
          "description": null,
          "data": {}
        }
      }
    }
    ```
*   **Response (503 Service Unavailable - Unhealthy):** Returned if the connection to `hyma_testdb` is timed out or authentication failed.
