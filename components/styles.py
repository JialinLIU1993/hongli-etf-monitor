"""CSS 样式常量"""

CUSTOM_CSS = """
<style>
    /* 主背景 - 纯白/极淡灰 */
    .stApp {
        background: #f8f9fa;
    }
    
    /* 侧边栏样式 */
    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid rgba(0, 0, 0, 0.05);
    }
    
    /* 毛玻璃卡片效果 (适配浅色背景) */
    .glass-card {
        background: rgba(255, 255, 255, 0.8);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(0, 0, 0, 0.05);
        border-radius: 8px;
        padding: 1.5rem;
        margin: 0.5rem 0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    }
    
    /* Metric 卡片增强 */
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid rgba(0, 0, 0, 0.05);
        border-radius: 8px;
        padding: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    }
    
    [data-testid="stMetricValue"] {
        color: #d97706; /* Amber-600 */
        font-size: 1.35rem;
        line-height: 1.25;
        font-weight: 700;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    
    [data-testid="stMetricLabel"] {
        color: #4b5563; /* Gray-600 */
        font-weight: 500;
    }
    
    /* 标题样式 */
    h1 {
        color: #1f2937 !important; /* Gray-900 */
        text-shadow: none;
    }
    
    h2, h3 {
        color: #374151 !important; /* Gray-700 */
        border-bottom: 2px solid #f3f4f6;
        padding-bottom: 0.5rem;
    }
    
    /* 按钮样式 */
    .stButton > button {
        background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
        color: #ffffff;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(245, 158, 11, 0.2);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(245, 158, 11, 0.3);
    }
    
    /* 表格样式 */
    .stDataFrame {
        background: #ffffff;
        border-radius: 8px;
        border: 1px solid #e5e7eb;
    }
    
    /* 信号卡片 */
    .signal-buy {
        background: #fef2f2; /* Red-50 */
        border: 1px solid #fecaca; /* Red-200 */
        border-radius: 8px;
        padding: 1rem;
        color: #991b1b;
    }
    
    .signal-sell {
        background: #f0fdf4; /* Green-50 */
        border: 1px solid #bbf7d0; /* Green-200 */
        border-radius: 8px;
        padding: 1rem;
        color: #166534;
    }
    
    .signal-hold {
        background: #eff6ff; /* Blue-50 */
        border: 1px solid #bfdbfe; /* Blue-200 */
        border-radius: 8px;
        padding: 1rem;
        color: #1e40af;
    }
    
    /* Tab 样式 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: #f3f4f6;
        border-radius: 12px;
        padding: 4px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        color: #6b7280;
        font-weight: 500;
    }
    
    .stTabs [aria-selected="true"] {
        background: #ffffff;
        color: #d97706;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* 隐藏 Streamlit 默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
"""
