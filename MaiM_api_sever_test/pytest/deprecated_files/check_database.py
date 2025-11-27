import sqlite3
import os

def check_database():
    db_path = 'data/MaiBot.db'
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表
        cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
        tables = cursor.fetchall()
        print('数据库表:', tables)
        
        # 检查agents表结构
        if ('agents',) in tables:
            cursor.execute('PRAGMA table_info(agents)')
            columns = cursor.fetchall()
            print('agents表结构:', columns)
            
            # 检查agent_templates表结构
            cursor.execute('PRAGMA table_info(agent_templates)')
            columns = cursor.fetchall()
            print('agent_templates表结构:', columns)
            
            # 检查tenant_users表结构
            cursor.execute('PRAGMA table_info(tenant_users)')
            columns = cursor.fetchall()
            print('tenant_users表结构:', columns)
        
        conn.close()
        print("数据库检查完成")
        
    except Exception as e:
        print(f"数据库检查失败: {e}")

if __name__ == "__main__":
    check_database()
