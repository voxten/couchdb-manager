import os
import json
from flask import Flask, request, render_template, redirect, url_for, send_file
import couchdb
import tempfile

app = Flask(__name__)

couch_host = os.getenv('COUCH_HOST')
couch_port = os.getenv('COUCH_PORT')
couch_user = os.getenv('COUCH_USER')
couch_pass = os.getenv('COUCH_PASSWORD')

url = f"http://{couch_user}:{couch_pass}@{couch_host}:{couch_port}"
couch_client = couchdb.Server(url)


@app.route('/')
def home():
    dbs = list(couch_client)
    return render_template('index.html', databases=dbs)


@app.route('/create_db', methods=['POST'])
def create_db():
    db_name = request.form.get('db_name')
    if db_name and db_name not in couch_client:
        couch_client.create(db_name)
    return redirect(url_for('home'))


@app.route('/upload_json_page')
def upload_json_page():
    return render_template('upload_json.html')


@app.route('/upload_json', methods=['POST'])
def upload_json():
    if 'json_file' not in request.files:
        return redirect(url_for('home'))

    json_file = request.files['json_file']
    if json_file.filename == '':
        return redirect(url_for('home'))

    if json_file and json_file.filename.endswith('.json'):
        try:
            data = json.load(json_file)
        except json.JSONDecodeError:
            return "Invalid JSON file", 400

        if isinstance(data, list):
            db_name = os.path.splitext(json_file.filename)[0]  # Extract the file name without extension
            if db_name and db_name not in couch_client:
                db = couch_client.create(db_name)
                for collection in data:
                    doc_id = collection.get('_id')
                    content = collection.get('content', [])
                    if doc_id:
                        db.save({"_id": doc_id, "content": content})
            else:
                return "Database name is required or already exists", 400
        else:
            return "Invalid JSON structure", 400

        return redirect(url_for('home'))
    else:
        return "Invalid file format", 400




@app.route('/rename_db/<db_name>', methods=['POST'])
def rename_db(db_name):
    new_db_name = request.form.get('new_db_name')
    if new_db_name and db_name in couch_client:
        db = couch_client[db_name]
        new_db = couch_client.create(new_db_name)
        for doc_id in db:
            doc = db.get(doc_id)
            if '_rev' in doc:
                del doc['_rev']
            new_db.save(doc)
        del couch_client[db_name]
    return redirect(url_for('home'))


@app.route('/view_db/<db_name>')
def view_db(db_name):
    if db_name in couch_client:
        db = couch_client[db_name]
        collections = []
        content_names = set()

        for doc_id in db:
            doc = db.get(doc_id)
            if doc and 'content' in doc:
                for content in doc['content']:
                    if 'name' in content:
                        content_names.add(content['name'])

        for doc_id in db:
            doc = db.get(doc_id)
            if doc:
                collection = {'_id': doc_id}
                for name in content_names:
                    content_desc = next(
                        (content['description'] for content in doc.get('content', []) if content.get('name') == name),
                        'null')
                    collection[name] = content_desc
                collections.append(collection)

        content_names = sorted(content_names)
        return render_template('view_db.html', db_name=db_name, collections=collections, content_names=content_names)
    return redirect(url_for('home'))


@app.route('/view_collection/<db_name>/<collection_id>')
def view_collection(db_name, collection_id):
    if db_name in couch_client:
        db = couch_client[db_name]
        doc = db.get(collection_id)
        if doc:
            content_list = doc.get('content', [])
            return render_template('view_collection.html', db_name=db_name, collection_id=collection_id, doc=doc,
                                   content_list=content_list)
    return redirect(url_for('view_db', db_name=db_name))


@app.route('/add_content/<db_name>/<collection_id>', methods=['POST'])
def add_content(db_name, collection_id):
    if db_name in couch_client:
        db = couch_client[db_name]
        doc = db.get(collection_id)
        if doc:
            content_name = request.form.get('content_name')
            content_description = request.form.get('content_description')
            if content_name and content_description:
                new_content = {"name": content_name, "description": content_description}
                if 'content' not in doc:
                    doc['content'] = []
                doc['content'].append(new_content)
                db.save(doc)
    return redirect(url_for('view_collection', db_name=db_name, collection_id=collection_id))


@app.route('/modify_content_name/<db_name>/<collection_id>/<content_index>', methods=['POST'])
def modify_content_name(db_name, collection_id, content_index):
    if db_name in couch_client:
        db = couch_client[db_name]
        doc = db.get(collection_id)
        if doc and 'content' in doc:
            new_name = request.form.get('new_name')
            if new_name:
                doc['content'][int(content_index)]['name'] = new_name
                db.save(doc)
    return redirect(url_for('view_collection', db_name=db_name, collection_id=collection_id))


@app.route('/modify_content_description/<db_name>/<collection_id>/<content_index>', methods=['POST'])
def modify_content_description(db_name, collection_id, content_index):
    if db_name in couch_client:
        db = couch_client[db_name]
        doc = db.get(collection_id)
        if doc and 'content' in doc:
            new_description = request.form.get('new_description')
            if new_description:
                doc['content'][int(content_index)]['description'] = new_description
                db.save(doc)
    return redirect(url_for('view_collection', db_name=db_name, collection_id=collection_id))


@app.route('/delete_content/<db_name>/<collection_id>/<content_index>', methods=['POST'])
def delete_content(db_name, collection_id, content_index):
    if db_name in couch_client:
        db = couch_client[db_name]
        doc = db.get(collection_id)
        if doc and 'content' in doc:
            try:
                index = int(content_index)
                if 0 <= index < len(doc['content']):
                    del doc['content'][index]
                    db.save(doc)
            except ValueError:
                pass
    return redirect(url_for('view_collection', db_name=db_name, collection_id=collection_id))


@app.route('/delete_db/<db_name>', methods=['POST'])
def delete_db(db_name):
    if db_name in couch_client:
        del couch_client[db_name]
    return redirect(url_for('home'))


@app.route('/create_collection/<db_name>', methods=['POST'])
def create_collection(db_name):
    collection_name = request.form.get('collection_name')
    if db_name in couch_client and collection_name:
        db = couch_client[db_name]
        if collection_name not in db:
            db.save({"_id": collection_name, "content": []})
        else:
            return "Collection with this name already exists", 409
    return redirect(url_for('view_db', db_name=db_name))


@app.route('/rename_collection/<db_name>/<collection_id>', methods=['POST'])
def rename_collection(db_name, collection_id):
    new_collection_id = request.form.get('new_collection_id')
    if db_name in couch_client:
        db = couch_client[db_name]
        doc = db.get(collection_id)
        if doc:
            doc['_id'] = new_collection_id
            if '_rev' in doc:
                del doc['_rev']
            db.save(doc)
            db.delete(db[collection_id])
    return redirect(url_for('view_db', db_name=db_name))


@app.route('/delete_collection/<db_name>/<collection_id>', methods=['POST'])
def delete_collection(db_name, collection_id):
    if db_name in couch_client:
        db = couch_client[db_name]
        doc = db.get(collection_id)
        if doc:
            db.delete(doc)
    return redirect(url_for('view_db', db_name=db_name))


@app.route('/export_db/<db_name>', methods=['GET'])
def export_db(db_name):
    if db_name in couch_client:
        db = couch_client[db_name]
        data = []
        for doc_id in db:
            doc = db.get(doc_id)
            if doc:
                # Exclude '_rev' field from exported data
                doc.pop('_rev', None)
                data.append(doc)

        # Create a temporary file and write data to it
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8') as tmp_file:
            json.dump(data, tmp_file, indent=4)
            tmp_file_path = tmp_file.name

        # Send the file to the user
        return send_file(tmp_file_path, as_attachment=True, download_name=f"{db_name}.json")

    return redirect(url_for('home'))



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
