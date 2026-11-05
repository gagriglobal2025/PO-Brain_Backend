# PO-Brain: Database Connection Configuration

This document contains the extracted connection parameters and ready-to-use connection string formats for various components of the **PO-Brain** system.

> [!IMPORTANT]
> **Security Notice**: This file contains sensitive production credentials. Ensure it is included in your `.gitignore` file and never committed to public repositories.

---

## 1. Extracted Connection Parameters

From the provided XML configuration:
```xml
<add name="contr" connectionString="Server=3.109.43.10,8016; Database=hyma_testdb; User Id=avrasynt_db; password=avra_1234" providerName="System.Data.SqlClient" />
```

We have extracted the following parameters:

| Parameter | Value | Description |
|---|---|---|
| **Host IP** | `3.109.43.10` | The external database server IP address |
| **Port** | `8016` | Custom MSSQL server communication port |
| **Database** | `hyma_testdb` | Target database for PO-Brain schemas |
| **User ID** | `avrasynt_db` | Authentication username |
| **Password** | `avra_1234` | Authentication password |
| **Provider** | `System.Data.SqlClient` / `Microsoft.Data.SqlClient` | Standard Microsoft SQL Server driver provider |

---

## 2. Ready-to-Use Connection Formats

### 2.1 C# .NET Core (AppSettings / EF Core)
Add this to your `appsettings.json` file in the Web API project:
```json
{
  "ConnectionStrings": {
    "POBrainConnection": "Server=3.109.43.10,8016;Database=hyma_testdb;User Id=avrasynt_db;Password=avra_1234;TrustServerCertificate=True;Encrypt=True;"
  }
}
```

### 2.2 Python (using `pyodbc`)
For Python pipelines, use this formatted connection string:
```python
import pyodbc

conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=3.109.43.10,8016;"
    "DATABASE=hyma_testdb;"
    "UID=avrasynt_db;"
    "PWD=avra_1234;"
    "Encrypt=yes;"
    "TrustServerCertificate=yes;"
)
conn = pyodbc.connect(conn_str)
```

### 2.3 Python (using `pymssql`)
If using lightweight `pymssql`:
```python
import pymssql

conn = pymssql.connect(
    server="3.109.43.10",
    port=8016,
    user="avrasynt_db",
    password="avra_1234",
    database="hyma_testdb"
)
```

### 2.4 Node.js / TypeScript (using `mssql`)
```javascript
const sql = require('mssql');

const config = {
    user: 'avrasynt_db',
    password: 'avra_1234',
    server: '3.109.43.10',
    port: 8016,
    database: 'hyma_testdb',
    options: {
        encrypt: true, // Use encryption
        trustServerCertificate: true // Trust self-signed certificates
    }
};

await sql.connect(config);
```

### 2.5 JDBC (Java)
```java
String connectionUrl = "jdbc:sqlserver://3.109.43.10:8016;databaseName=hyma_testdb;user=avrasynt_db;password=avra_1234;encrypt=true;trustServerCertificate=true;";
```
