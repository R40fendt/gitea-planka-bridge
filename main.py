from plankapy.v2 import Planka
from flask import Flask, request
import mysql.connector
import os


planka = Planka(os.getenv("PLANKA_URL"))
planka.login(
    username=os.getenv("PLANKA_USER"),
    password=os.getenv("PLANKA_PASSWORD"),
    accept_terms=True
)

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST") or "db",
    user=os.getenv("DB_USER") or "app",
    password=os.getenv("DB_PASSWORD") or "app",
    database=os.getenv("DB_NAME") or "app"
)

conn.cursor().execute("CREATE TABLE IF NOT EXISTS issue_mapping (gitea_issue_id INT PRIMARY KEY, planka_card_id VARCHAR(255) NOT NULL)")
conn.cursor().execute("CREATE TABLE IF NOT EXISTS repo_mapping (gitea_repo VARCHAR(255) PRIMARY KEY, project VARCHAR(255) NOT NULL, board VARCHAR(255) NOT NULL, list VARCHAR(255) NOT NULL)")

app = Flask(__name__)

def insert_issue(issue, repo_full_name):
    planka_list=get_planka_list_by_repo(repo_full_name)
    print("Inserting issue ",issue["id"]," into Planka list",planka_list.name)

    card=planka_list.create_card(name=issue["title"], description=issue["body"] or "")
    return card.id

def get_planka_list_by_repo(repo_full_name):
    cursor=conn.cursor()
    cursor.execute("SELECT project, board, list FROM repo_mapping WHERE gitea_repo=%s", (repo_full_name,))
    result=cursor.fetchone()
    if result:
        return get_planka_list(result[0], result[1], result[2])
    return None

def get_planka_card_by_repo(repo_full_name, card_id):
    planka_board=get_planka_list_by_repo(repo_full_name).board
    for card in planka_board.cards:
        if card.id==card_id:
            return card
    return None

def get_planka_card_by_issue_id(repo_full_name,issue_id):
    cursor=conn.cursor()
    cursor.execute("SELECT planka_card_id FROM issue_mapping WHERE gitea_issue_id=%s", (issue_id,))
    result=cursor.fetchone()
    if result:
        card_id=result[0]
        return get_planka_card_by_repo(repo_full_name, card_id)
 

def add_dependency(issue_id, repo_full_name, dependency_issue_id):
    card=get_planka_card_by_issue_id(repo_full_name, issue_id)
    dependency_card=get_planka_card_by_issue_id(repo_full_name, dependency_issue_id)
    if card and dependency_card:
        pass
        if len(card.task_lists)==0:
            task_list=card.create_task_list("Dependencies")
        else:
            task_list=card.task_lists[0]
        task_list.add_task(linked_card=dependency_card)
    else:
        print("No Planka card found for issue ",issue_id," or dependency issue ",dependency_issue_id)





def insert_comment(comment, issue_id, repo_full_name):
    card=get_planka_card_by_issue_id(repo_full_name, issue_id)
    if card: card.comment(comment["body"])
    else:
        print("No Planka card found for issue ",issue_id)

def get_planka_board(planka_project, planka_board):
    for project in planka.projects:
        if project.id==planka_project:
            for board in project.boards:
                if board.id==planka_board:
                    return board
    return None
    
def get_planka_list(planka_project, planka_board, planka_list):
    for project in planka.projects:
        if project.id==planka_project:
            for board in project.boards:
                if board.id==planka_board:
                    for lst in board.lists:
                        if lst.id==planka_list:
                            return lst
    return None


                            
@app.route("/map/<user>/<repo>/<planka_project>/<planka_board>/<planka_list>",methods=["GET"])
def map(user,repo,planka_project,planka_board,planka_list):
    print("Mapping repository ",user,"/",repo," to Planka project ",planka_project," board ",planka_board," list ",planka_list)
    
    lst=get_planka_list(planka_project, planka_board, planka_list)
    if lst:
        print("Found Planka list ",lst.name)
    else: 
        return "Planka list not found"
    try:
        cursor=conn.cursor()
        cursor.execute("INSERT INTO repo_mapping (gitea_repo,project,board,list) VALUES (%s,%s,%s,%s)", (f"{user}/{repo}", planka_project, planka_board, planka_list))
        conn.commit()
        return "ok"
    except mysql.connector.IntegrityError:
        return "Mapping already exists"

@app.route("/webhook",methods=["POST"])
def webhook():
    print("Received webhook")
    event=request.headers.get("X-Gitea-Event")

    data=request.json

    print("Received event: ",event)
    print("Received data: ",data)

    if event=="issue_comment":
        if data["action"]=="created":
            print("New comment: ",data["comment"])
            insert_comment(data["comment"],data["issue"]["id"],data["repository"]["full_name"])
            
    elif event=="issues":
        if data["action"]=="opened":
            print("New issue: ",data["issue"])
            conn.cursor().execute("INSERT INTO issue_mapping (gitea_issue_id, planka_card_id) VALUES (%s, %s)", (data["issue"]["id"], insert_issue(data["issue"],data["repository"]["full_name"])))
            conn.commit()


    return "ok"




app.run(host="0.0.0.0",port=8093)