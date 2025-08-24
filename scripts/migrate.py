import psycopg2

from loguru import logger
from os import environ
from psycopg2.extras import execute_values

conn1 = psycopg2.connect(
    dbname=environ.get('source_db_name'),
    user=environ.get('source_db_user'),
    password=environ.get("source_db_password", ""),
    host=environ.get("source_db_host", 'localhost'),
    port=environ.get("source_db_port", '5432')
)
conn2 = psycopg2.connect(
    dbname=environ.get('target_db_name'),
    user=environ.get("target_db_user"),
    password=environ.get("target_db_password", ''),
    host=environ.get("target_db_host", 'localhost'),
    port=environ.get("target_db_port", '5432')
)

start_id = 0
cur2 = conn2.cursor()
cur2.execute("select id from channel_news order by id desc limit 1 ")
rows = cur2.fetchone()
if rows is not None:
    start_id = rows[0]

end_id = 0
cur1 = conn1.cursor()
cur1.execute("select id from channel_news order by id desc limit 1 ")
rows = cur1.fetchone()
if rows is not None:
    end_id = rows[0]
logger.info("Start migrating channel_news, start_id: {}, end_id: {}", start_id, end_id)
cur1.close()
cur1 = conn1.cursor(name="cur1")
cur2 = conn2.cursor()
cur1.execute("""select cn.id, cn.message_id, cn.chat_id, cn.group_name, cn.message_text, cn.urls, cn."timestamp"
                from channel_news cn
                where id > %s
                  and id <= %s
                order by id asc""", (start_id, end_id))
while True:
    rows = cur1.fetchmany(size=100)
    if not rows:
        break
    sql = "insert into channel_news (id, message_id, chat_id, group_name, message_text, urls, timestamp) values %s"
    execute_values(cur2, sql, rows, page_size=1000)
    conn2.commit()

cur1.close()
# cur1 = conn1.cursor()
# cur1.execute("delete from channel_news where id >= %s and id <= %s ", (start_id, end_id))
conn1.commit()
logger.info("Migrated channel_news")
# cur1.close()
cur2.close()

###########################

start_id = 0
cur2 = conn2.cursor()
cur2.execute("select id from chat_messages order by id desc limit 1 ")
rows = cur2.fetchone()
if rows is not None:
    start_id = rows[0]

end_id = 0
cur1 = conn1.cursor()
cur1.execute("select id from chat_messages order by id desc limit 1 ")
rows = cur1.fetchone()
if rows is not None:
    end_id = rows[0]
logger.info("Start migrating chat_messages, start_id: {}, end_id: {}", start_id, end_id)
cur1.close()
cur1 = conn1.cursor(name="cur1")
cur2 = conn2.cursor()
cur1.execute("""select cn.id, cn.message_id, cn.chat_id, cn.group_name, cn.sender_id, cn.message_text, cn.urls, cn."timestamp"
                from chat_messages cn
                where id > %s
                  and id <= %s
                order by id asc""", (start_id, end_id))
while True:
    rows = cur1.fetchmany(size=1000)
    if not rows:
        break
    sql = ("insert into chat_messages (id, message_id, chat_id, group_name, sender_id, message_text, urls, timestamp) "
           "values %s")
    execute_values(cur2, sql, rows, page_size=1000)
    conn2.commit()

cur1.close()
# cur1 = conn1.cursor()
# cur1.execute("delete from chat_messages where id >= %s and id <= %s ", (start_id, end_id))
conn1.commit()
logger.info("Migrated chat_messages")
# cur1.close()
cur2.close()
######################

start_id = 0
cur2 = conn2.cursor()
cur2.execute("select id from link_content order by id desc limit 1 ")
rows = cur2.fetchone()
if rows is not None:
    start_id = rows[0]

end_id = 0
cur1 = conn1.cursor()
cur1.execute("select id from link_content order by id desc limit 1 ")
rows = cur1.fetchone()
if rows is not None:
    end_id = rows[0]
logger.info("Start migrating link_content, start_id: {}, end_id: {}", start_id, end_id)
cur1.close()
cur1 = conn1.cursor(name="cur1")
cur2 = conn2.cursor()
cur1.execute("""select cn.id, cn.related_super_group_id, cn.url, cn.title, cn.content, cn."timestamp"
                from link_content cn
                where id > %s
                  and id <= %s
                order by id asc""", (start_id, end_id))
while True:
    rows = cur1.fetchmany(size=1000)
    if not rows:
        break
    sql = ("insert into link_content (id, related_super_group_id, url, title, content, timestamp) "
           "values %s")
    execute_values(cur2, sql, rows, page_size=1000)
    conn2.commit()

cur1.close()
# cur1 = conn1.cursor()
# cur1.execute("delete from link_content where id >= %s and id <= %s ", (start_id, end_id))
conn1.commit()
logger.info("Migrated link_content")
# cur1.close()
cur2.close()
######################
conn1.close()
conn2.close()
