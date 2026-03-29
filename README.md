# 💼 ReimburseFlow - Expense Reimbursement Management System

A comprehensive, enterprise-grade expense reimbursement management system built with Flask. Features multi-level approval workflows, OCR receipt scanning, multi-currency support, and role-based access control.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🌟 Features

### Core Functionality

#### 🔐 Authentication & User Management
- **First-time Setup**: Auto-creates company and admin account on signup
- **Multi-currency Support**: Automatic currency detection based on country selection
- **Role Management**: Three distinct roles (Admin, Manager, Employee)
- **User Hierarchy**: Define manager-employee relationships
- **Full CRUD**: Complete user management capabilities

#### 💰 Expense Management
- **Multi-currency Expenses**: Submit expenses in any currency with automatic conversion
- **Rich Expense Data**:
  - Amount and currency
  - Category (11 predefined categories)
  - Description and vendor information
  - Expense date
  - Receipt upload (images/PDF)
- **Expense Tracking**: View complete history with status indicators
- **Expense Actions**: Cancel pending/draft expenses

#### ✅ Advanced Approval Workflows
- **Sequential Approval**: Multi-level approval chains (Step 1 → Step 2 → Step 3)
- **Manager-First Option**: Automatically add employee's manager as first approver
- **Flexible Approver Assignment**: Define custom approval sequences
- **Approval Visualization**: Real-time approval chain progress tracking
- **Comments**: Add comments at each approval stage

#### 🎯 Role-Based Permissions

**Admin**
- Create and manage company settings
- Full user management (create, edit, delete users)
- Configure approval rules
- View all expenses across the organization
- Override any approval (force approve/reject)

**Manager**
- Approve/reject expenses in approval queue
- View amounts in company's default currency
- Track team expenses (subordinates)
- Add comments to approvals
- View approval history

**Employee**
- Submit expense claims
- View personal expense history
- Track approval status
- Cancel pending expenses
- Upload receipts

### 🚀 Advanced Features

#### 📸 OCR Receipt Scanning
- **Automatic Data Extraction**: Upload receipt images for automatic field population
- **Smart Detection**:
  - Amount extraction
  - Date parsing (multiple formats)
  - Vendor identification
  - Category suggestion based on keywords
- **Supported Formats**: PNG, JPG, JPEG, GIF, WebP, PDF

#### 💱 Currency Management
- **Real-time Conversion**: Automatic currency conversion using live exchange rates
- **Dual Display**: Show both original and converted amounts
- **API Integration**:
  - Country/Currency API: `https://restcountries.com/v3.1/all`
  - Exchange Rate API: `https://api.exchangerate-api.com/v4/latest/{currency}`

#### 🎨 Modern UI/UX
- **Professional Design**: Clean, minimalist interface with Poppins font
- **Dark Theme**: Easy on the eyes with professional blue accents (#2563eb)
- **Responsive**: Works seamlessly on desktop and mobile devices
- **Visual Feedback**: Status badges, progress indicators, and approval chains
- **Custom SVG Icons**: Professional briefcase logo throughout

## 📋 Tech Stack

- **Backend**: Flask 2.0+
- **Database**: SQLite (SQLAlchemy ORM)
- **Authentication**: Flask-Login with password hashing
- **OCR**: Tesseract OCR with pytesseract
- **Image Processing**: Pillow (PIL)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Fonts**: Google Fonts (Poppins)

## 🛠️ Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Tesseract OCR (optional, for receipt scanning)

### Step 1: Clone the Repository
```bash
git clone <repository-url>
cd Reimbursement-Management-Odoo-VITPune-Hackathon
```

### Step 2: Create Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Install Tesseract OCR (Optional)
**Windows:**
- Download from: https://github.com/UB-Mannheim/tesseract/wiki
- Add to PATH

**Linux:**
```bash
sudo apt-get install tesseract-ocr
```

**Mac:**
```bash
brew install tesseract
```

### Step 5: Run the Application
```bash
python run.py
```

The application will be available at `http://localhost:5000`

## 🚀 Quick Start Guide

### First-Time Setup

1. **Navigate to** `http://localhost:5000`
2. **Click** "Set up your company"
3. **Fill in**:
   - Admin name and email
   - Password
   - Company name
   - Country (currency auto-detected)
4. **Click** "Create Company & Admin"

### Creating Users (Admin)

1. **Login** as admin
2. **Go to** Admin Dashboard → Users tab
3. **Click** "+ Add User"
4. **Fill in** user details and assign role
5. **Optionally** assign a manager

### Creating Approval Rules (Admin)

1. **Go to** Admin Dashboard → Approval Rules tab
2. **Click** "+ New Rule"
3. **Configure**:
   - Rule name
   - Check "IS MANAGER APPROVER" if needed
   - Add approver sequence (Step 1, 2, 3...)
   - Set conditional rules (optional)
4. **Click** "Create Rule"

### Submitting Expenses (Employee)

1. **Login** as employee
2. **Click** "+ Submit Expense"
3. **Upload** receipt (optional - OCR will auto-fill)
4. **Fill in** expense details
5. **Select** approval rule
6. **Click** "Submit Expense"

### Approving Expenses (Manager)

1. **Login** as manager
2. **View** pending approvals
3. **Review** expense details
4. **Add** comment (optional)
5. **Click** "✓ Approve" or "✕ Reject"

## 📁 Project Structure

```
Reimbursement-Management-Odoo-VITPune-Hackathon/
│
├── app/
│   ├── __init__.py              # Flask app initialization
│   ├── models.py                # Database models
│   ├── utils.py                 # Helper functions
│   ├── ocr.py                   # OCR receipt processing
│   │
│   ├── routes/
│   │   ├── auth.py              # Authentication routes
│   │   ├── admin.py             # Admin dashboard routes
│   │   ├── employee.py          # Employee routes
│   │   └── manager.py           # Manager approval routes
│   │
│   ├── static/
│   │   ├── style.css            # Application styles
│   │   └── uploads/             # Receipt uploads
│   │
│   └── templates/
│       ├── base.html            # Base template
│       ├── auth/                # Login/Signup pages
│       ├── admin/               # Admin dashboard
│       ├── employee/            # Employee dashboard
│       ├── manager/             # Manager dashboard
│       └── errors/              # Error pages
│
├── instance/
│   └── reimbursement.db         # SQLite database
│
├── requirements.txt             # Python dependencies
├── run.py                       # Application entry point
├── CHECKLIST.md                 # Feature checklist
└── README.md                    # This file
```

## 🗄️ Database Schema

### Models

**Company**
- id, name, country, currency_code, currency_symbol, created_at

**User**
- id, name, email, password_hash, role, company_id, manager_id, created_at

**ApprovalRule**
- id, name, company_id, manager_is_first_approver, approval_percentage, specific_approver_id, created_at

**ApprovalStep**
- id, rule_id, approver_id, step_order

**Expense**
- id, employee_id, company_id, rule_id, title, description, category, amount, currency, amount_in_company_currency, expense_date, receipt_filename, vendor, status, current_step, created_at, updated_at

**ExpenseApproval**
- id, expense_id, approver_id, step_order, status, comment, acted_at

## 🔒 Security Features

- **Password Hashing**: Werkzeug secure password hashing
- **Session Management**: Flask-Login secure sessions
- **Role-Based Access Control**: Decorator-based route protection
- **CSRF Protection**: Built-in Flask form protection
- **File Upload Validation**: Restricted file types and sizes

## 🎯 Use Cases

### Scenario 1: Simple Approval
1. Employee submits expense
2. Manager approves
3. Expense marked as approved

### Scenario 2: Multi-Level Approval
1. Employee submits expense
2. Direct manager approves (Step 1)
3. Finance manager approves (Step 2)
4. Director approves (Step 3)
5. Expense marked as approved

### Scenario 3: Admin Override
1. Employee submits expense
2. Stuck in approval chain
3. Admin force approves/rejects
4. All pending approvals marked as skipped

## 📊 Expense Categories

- Travel
- Accommodation
- Meals & Entertainment
- Office Supplies
- Software & Subscriptions
- Training & Education
- Marketing
- Equipment
- Utilities
- Medical
- Miscellaneous

## 🌐 API Endpoints

### Authentication
- `GET /` - Home/redirect
- `GET/POST /signup` - Company setup
- `GET/POST /login` - User login
- `GET /logout` - User logout

### Admin Routes
- `GET /admin/dashboard` - Admin dashboard
- `POST /admin/users/create` - Create user
- `POST /admin/users/<id>/edit` - Edit user
- `POST /admin/users/<id>/delete` - Delete user
- `POST /admin/rules/create` - Create approval rule
- `POST /admin/rules/<id>/delete` - Delete rule
- `POST /admin/expenses/<id>/override` - Override approval

### Employee Routes
- `GET /employee/dashboard` - Employee dashboard
- `POST /employee/submit` - Submit expense
- `POST /employee/expenses/<id>/cancel` - Cancel expense
- `POST /employee/ocr` - OCR receipt processing
- `GET /employee/convert-currency` - Currency conversion

### Manager Routes
- `GET /manager/dashboard` - Manager dashboard
- `POST /manager/expenses/<id>/action` - Approve/reject expense

## 🐛 Troubleshooting

### OCR Not Working
- Ensure Tesseract is installed and in PATH
- Check pytesseract installation: `pip install pytesseract`
- Verify image format is supported

### Currency Conversion Fails
- Check internet connection
- API might be rate-limited
- Falls back to original amount if conversion fails

### Database Issues
- Delete `instance/reimbursement.db` to reset
- Run `python run.py` to recreate database

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License.

## 👥 Authors

- **Team ReimburseFlow** : Arnav, Akash, Sahil - Odoo x VIT Pune Hackathon 2026

## 🙏 Acknowledgments

- Flask framework and community
- Tesseract OCR project
- RestCountries API
- ExchangeRate API
- Google Fonts (Poppins)
