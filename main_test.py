from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from dotenv import load_dotenv
import mysql.connector
import json
from new_test import extract_text, clean_output, crew, summarization_task, interview_task, evaluation_task, editor_task, output_parser_task
import os
import pandas as pd
import uuid
import tempfile
import logging
import json
import datetime, traceback

# Flask app configuration
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

app.config['UPLOAD_FOLDER'] = 'uploads/'  # Directory for uploaded files
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit file size to 16 MB
app.secret_key = 'a_super_secret_key_12345'  # Use a secure random string
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# MySQL Configuration
app.config['MYSQL_HOST'] = os.getenv("MYSQL_HOST")
app.config['MYSQL_USER'] = os.getenv("MYSQL_USER")
app.config['MYSQL_PASSWORD'] = os.getenv("MYSQL_PASSWORD")
app.config['MYSQL_DB'] = os.getenv("MYSQL_DB")
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

def insert_results_into_db(results):
    try:
        cur = mysql.connection.cursor()
        for resume_list in results:
            for resume in resume_list:
                cur.execute("""
                    INSERT INTO hr_resume_results (
                        candidate_name,
                        overall_score,
                        tag,
                        explanation,
                        feedback
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (
                    resume.get('candidate_name'),
                    resume.get('overall_score'),
                    resume.get('tag'),
                    resume.get('explanation'),
                    resume.get('feedback')
                ))
        mysql.connection.commit()
        cur.close()
        print("✅ All results inserted successfully into the database.")
    except Exception as e:
        print("❌ Error inserting results:")
        traceback.print_exc()


def save_file(file, upload_folder):
    """
    Save an uploaded file to the specified folder and return the file path.
    """
    try:
        if not file or file.filename == '':
            raise ValueError("File is missing.")
        file_path = os.path.join(upload_folder, file.filename)
        file.save(file_path)
        logging.info(f"File saved at: {file_path}")
        return file_path
    except Exception as e:
        logging.error(f"Error saving file: {e}")
        raise

def read_temp_file(file_path):
    """
    Read the content of a temporary file and return its contents.
    """
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        logging.error(f"Error reading temporary file: {e}")
        raise

@app.route('/', methods=['GET', 'POST'])
def home():
    error = None
    try:
        if request.method == 'POST':
            # Check if the user wants to retain the existing job description
            retain_job_desc = 'retain_job_desc' in request.form

            # Process job description
            if not retain_job_desc or not os.path.exists(session.get('job_description_file', '')):
                job_desc_file = request.files.get('job_desc')
                if not job_desc_file or job_desc_file.filename == '':
                    raise ValueError("Job description file is required.")
                job_desc_path = save_file(job_desc_file, app.config['UPLOAD_FOLDER'])
                session['job_description_file'] = job_desc_path  # Save job description file path in session
                session['file_name'] = job_desc_file.filename
            else:
                logging.info("Reusing existing job description.")

            print("Job description file path:", session.get('job_description_file'))
            
            # Process multiple resumes
            resume_files = request.files.getlist('resumes')  # Get list of resume files
            if not resume_files or all(file.filename == '' for file in resume_files):
                raise ValueError("At least one resume file is required.")

            # Store results for all resumes
            all_results = []
            job_description_path = session.get('job_description_file')
            job_description = extract_text(job_description_path)

            # 🔄 Clear existing results before inserting new ones
            cur = mysql.connection.cursor()
            cur.execute("TRUNCATE TABLE hr_resume_results")
            mysql.connection.commit()
            cur.close()
            logging.info("🔄 Cleared previous results from hr_resume_results.")


            for resume_file in resume_files:
                if resume_file.filename != '':
                    resume_path = save_file(resume_file, app.config['UPLOAD_FOLDER'])
                if not resume_file.filename.lower().endswith(('.pdf', '.docx', '.txt')):
                    print(f"Skipping unsupported file format: {resume_file.filename}")
                    continue

                print(f"\nProcessing resume: {resume_file.filename}")
                try:
                    resume_text = extract_text(resume_path)

                    result = crew.kickoff(inputs={
                        "resume": resume_text,
                        "job_description": job_description
                    })                    

                    parsed_output = clean_output(output_parser_task.output.raw)

                    # # ⬇️ Store into all_results
                    try:
                        all_results.append(json.loads(parsed_output))
                    except json.JSONDecodeError as e:
                            print(f"⚠️ Failed to parse JSON for {resume_file.filename}: {e}")
                            continue

                except Exception as e:
                    print(f"Error processing {resume_file.filename}: {e}")

            insert_results_into_db(all_results)

            return redirect(url_for('results'))

    except ValueError as ve:
        error = str(ve)  # Specific error message for validation errors
        logging.warning(f"Validation error: {error}")
    except Exception as e:
        error = "An unexpected error occurred. Please try again."
        logging.error(f"Unexpected error: {e}", exc_info=True)

    # Render the home page with error messages if any
    return render_template('base1.html', error=error, 
                           current_job_desc=session.get('job_description_file'),
                           current_file_name=session.get('file_name'))

@app.route('/results')
def results():
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT candidate_name, overall_score, tag, explanation, feedback FROM hr_resume_results ORDER BY overall_score DESC")
        results = cur.fetchall()
        cur.close()

        print(results)

        return render_template('result1.html', results=results)
    except Exception as e:
        logging.error(f"Error fetching results: {e}")
        return render_template('result1.html', results=[], error="Failed to load results.")
    
if __name__ == "__main__":
    # Start the Flask application
    app.run(host='0.0.0.0', debug=True, port=8000)