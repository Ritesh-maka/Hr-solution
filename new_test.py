import sys
import fitz
import re
import json
import argparse
from docx import Document
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
import datetime
from IPython.display import Markdown, display
import uuid

load_dotenv()
api_key = os.getenv('OPENAI_API_KEY')

llm = ChatOpenAI(
    model='gpt-4o',
    temperature=0.1,
    api_key=api_key
)

summarizer = Agent(
    role="Resume Summarizer",
    goal="Extract and summarize key qualifications, experiences, and skills from the {resume}.",
    backstory="You're tasked with summarizing {resume} for job applications. "
              "Your job is to condense the information in a resume into a clear and concise summary, "
              "highlighting the most relevant skills, experiences, and qualifications for potential employers. "
              "This summary will help recruiters quickly assess candidate suitability for job roles.",
    llm=llm,
    allow_delegation=False,
    verbose=True
)

summarization_task = Task(
    description=(
        "1. Extract the following key sections from the {resume}:\n"
        "   - Personal details (e.g., name, contact info)\n"
        "   - Education (degree, institution, year)\n"
        "   - Professional Years of exreprience (mandatory field - if not given calculate from the details given)\n"
        "   - Previous job titles \n"
        "   - Experience (job title, company, duration, key achievements)\n"
        "   - Skills (technical and overall skills)\n"
        "   - Certifications (if any)\n"
        "2. Summarize each section in a clear and concise manner.\n"
        "3. Ensure the summary highlights quantifiable achievements, relevant work experience, and specific skills.\n"
        "4. Organize the summary by section to make it easy for recruiters to assess."
    ),
    expected_output="A structured summary document with the following sections: "
                    "Personal Details, Education, Experience, Skills, Certifications.",
    agent=summarizer
)

evaluation_agent = Agent(
    role="Resume Evaluator",
    goal="Evaluate the summarized resume against the provided {job_description}, assess the overall fit, and provide feedback.",
    backstory="You are tasked with assessing whether a candidate is a good fit for a job based on their summarized resume. Your evaluation should focus on matching the candidate’s professional experience, educational background, skills, achievements, and certifications with the job description.",
    llm=llm,
    allow_delegation=False,
    verbose=True
)

evaluation_task = Task(
    description=(
        "1. Review the resume summary provided by the summarizer.\n"
        "2. Compare the candidate’s professional experience and educational background in the {resume} with the {job_description}. Use the following conditions to evaluate a score out of 100:\n"
        
        "       a - **Experience Check**: Evaluate the candidate's years of experience from the summary against the years of experience required in the {job_description}.\n"
        "               - Interpret experience requirements accurately for both range-based and open-ended criteria:\n"
        "                       - **If the job description specifies a range** (e.g., 'X-Y years'):\n"
        "                               - Candidates with experience **within this range** (from X to Y years, inclusive) are a proper match.\n"
        "                               - Only candidates with experience **exceeding the upper limit of the range** (i.e., more than Y years) should be tagged as 'OVERQUALIFIED.'\n"
        "                       - **If the job description specifies an open-ended requirement** (e.g., 'X+ years'):\n"
        "                               - Candidates with **X years or more** are a proper match and should not be tagged as 'OVERQUALIFIED.'\n"
        "                               - Ensure candidates with exactly X years meet the requirement without being overqualified.\n"
        "                       - **If the candidate specifies an open-ended experience** (e.g., 'X+ years'):\n"
        "                               - Interpret the candidate's experience as a minimum of X years.\n"
        "                               - Only consider them 'OVERQUALIFIED' if their experience significantly exceeds the specified job requirement.\n"
        "               - If mandatory experience or education is missing, assign a score below 20.\n"
        
        "       b - **Title Alignment Check**: Evaluate the candidate’s previous job titles from the summary in relation to the required job title in the {job_description}:\n"
        "               - **Important Condition for All Candidates (Both Freshers and Experienced):**\n"
        "                       - The candidate's previous job or internship titles must directly match the job title specified in the job description.\n"
        "                       - If there is **no match between prior titles (job or internship) and the required job title**, assign a score **below 40, regardless of skill relevance**.\n"
        
        "               - **For Candidates with Less Than 5 Years of Experience (including freshers):**\n"
        "                       - If their **most recent job or internship title** does not match the required job title, assign a score below 50.\n"
        
        "               - **For Candidates with 6-10 Years of Experience:**\n"
        "                       - Check the last two job titles.\n"
        "                       - If **atleast one of the last two job titles** matches the required job title, then consider it a match and assign a score above 70.\n"
        
        "       c - **Overall Suitability**: Only if the candidate meets all previous criteria (experience, education, and title alignment) then:\n"
        "               - Assess the resume based on the candidate’s skills, achievements, and certifications.\n"
        "               - However, if **any one of the above conditions is not met**, the resume must receive a score below 50, regardless of skills, certifications, or education.\n"
    ),
    expected_output=(
        "OVERALL SCORE - Provide a score between 0-100, based on the conditions outlined in the description.\n"
        "TAG - Specify 'OVERQUALIFIED' if applicable; otherwise, return 'QUALIFIED' if score greater than 75 and 'NOT QUALIFIED' if score less than 75.\n"
        "Provide a brief explanation of how the score is awarded."
    ),
    agent=evaluation_agent,
    context=[summarization_task]
)

interview_agent = Agent(
    role="Interview Question Generator",
    goal="Generate a set of interview questions based on the provided {job_description} only if the overall score from the evaluation_task is above 70 if not then print not suitable.",
    backstory="You are tasked with preparing interview questions for candidates based on the job description and the resume summary. The questions should assess relevant skills, qualifications, and experiences required for the role.",
    llm=llm,
    allow_delegation=False,
    verbose=True
)

interview_task = Task(
    description=(
        "1. Review the job description and the candidate's summarized resume provided.\n"
        "2. Check the overall score and tag from the evaluation task and proceed as follows:\n"
        "\n"
        "   a - If the score is less than 75:\n"
        "       - Return: 'Not suitable resume'\n"
        "\n"
        "   b - If the score is 75 or above:\n"
        "       - If TAG is 'OVERQUALIFIED':\n"
        "           - Return: 'resume is OVER QUALIFIED'\n"
        "\n"
        "       - If TAG is 'QUALIFIED':\n"
        "           - Generate personalized interview questions using both the job description and the candidate's resume summary.\n"
        "           - Tailor the questions to the candidate's specific skills, experiences, and achievements.\n"
        "           - Cover technical knowledge, problem-solving, behavioral fit, and relevant certifications.\n"
    ),
    expected_output=(
        "If score < 75: 'Not suitable resume'\n"
        "If TAG is 'OVERQUALIFIED': 'resume is OVER QUALIFIED'\n"
        "If TAG is 'QUALIFIED': A list of personalized interview questions based on the job description and resume.\n"
    ),
    agent=interview_agent,
    context=[evaluation_task, summarization_task]  # ✅ Add summarization_task for resume summary
)


editor_agent = Agent(
    role="Structured Output Editor",
    goal="Edit the outputs from the evaluation and interview agents into a standardized format for consistent user experience.",
    backstory="You are an editor responsible for refining outputs from the resume evaluation and interview question generation agents. Your objective is to ensure each response follows the designated format, allowing users to quickly interpret scores, feedback, and questions consistently.",
    llm=llm,
    allow_delegation=False,
    verbose=True
)

editor_task = Task(
    description=(
        "1. For the evaluation agent’s output:\n"
        "   - Format as follows:\n"
        "       CANDIDATE NAME: (get candidate name from summarization task that does the summary of the resume) \n"
        "       OVERALL SCORE \n"
        "       TAG \n"
        "       EXPLANATION OF SCORE AWARDED\n"
        "   - Ensure clarity and concise explanation.\n"
        "\n"
        "2. For the interview agent’s output:\n"
        "   - If the resume is not suitable, return: 'Not suitable resume'.\n"
        "   - If suitable with QUALIFIED tag, return: provide a line-by-line list of interview questions.\n"
        "   - If suitable with an OVER QUALIFIED tag, return: resume is OVER QUALIFIED\n"
        "Output should be in markdown format, ready for final review and publishing."
    ),
    expected_output=(
        "Standardized response format:\n"
        "Evaluation Result:\n"
        "   - CANDIDATE NAME\n"
        "   - OVERALL SCORE\n"
        "   - TAG\n"
        "   - EXPLANATION OF SCORE AWARDED\n"
        "Feedback:\n"
        "   - Interview agents output."
    ),
    agent=editor_agent,
    context=[summarization_task, evaluation_task, interview_task]
)

output_parser_agent = Agent(
    role="Output Parser",
    goal="Extract overall score, tag, explanation of score awarded, and feedback from the editor_task output and store them in a structured dictionary format.",
    backstory="You are an expert in parsing structured text outputs. Your role is to extract specific fields (overall score, tag, explanation, and feedback) from the editor agent's markdown output and organize them into a dictionary for each resume. The results will be collected in a list of dictionaries for further processing.",
    llm=llm,
    allow_delegation=False,
    verbose=True
)

output_parser_task = Task(
    description=(
        "1. Parse the markdown output from the editor_task for each resume.\n"
        "2. Extract the following fields:\n"
        "   - Candidate_name: The name of the candidate.\n"
        "   - overall_score: The numerical score (0-100) from the 'OVERALL SCORE' section.\n"
        "   - tag: The tag value (e.g., 'QUALIFIED', 'NOT QUALIFIED', 'OVERQUALIFIED') from the 'TAG' section.\n"
        "   - explanation: The text under 'EXPLANATION OF SCORE AWARDED' section.\n"
        "   - feedback: The text under the 'Feedback' section, including interview questions or status messages (e.g., 'Not suitable resume' or 'resume is OVER QUALIFIED').\n"
        "3. Store the extracted fields in a dictionary.\n"
        "4. Append each dictionary to a list to collect results for all resumes.\n"
    ),
    expected_output=(
        "A list of dictionaries, where each dictionary contains each of the below values:\n"
        # "   - resume_filename: The name of the resume file.\n"
        "   - candidate_name: The name of the candidate.\n"
        "   - overall_score: The numerical score (0-100).\n"
        "   - tag: The tag value (QUALIFIED, NOT QUALIFIED, or OVERQUALIFIED).\n"
        "   - explanation: The explanation text for the score.\n"
        "   - feedback: The feedback text, including interview questions or status messages."
        "NOTE : I need it in a proper JSON format, so please ensure the output is valid JSON."
    ),
    agent=output_parser_agent,
    context=[editor_task]
)

def extract_text(fname):
    file_extension = fname.split('.')[-1].lower()
    
    if file_extension == 'pdf':
        doc = fitz.open(fname)
        text = ""
        for page in doc:
            text += str(page.get_text())
        tx = " ".join(text.split('\n'))
        return tx

    elif file_extension == 'txt':
        with open(fname, 'r', encoding='utf-8') as file:
            return file.read()

    elif file_extension == 'docx':
        doc = Document(fname)
        text = []
        for para in doc.paragraphs:
            text.append(para.text)
        return ' '.join(text)

    else:
        raise ValueError("Unsupported file format. Please use PDF, TXT, or DOCX.")
    
def clean_output(text):
    lines = text.strip().splitlines()
    cleaned = [line for line in lines if not line.strip().startswith("```")]
    return "\n".join(cleaned)

def load_results_and_ranks(all_results):
    # Step 1: Flatten the list
    flat_results = [item[0] for item in all_results]

    print(flat_results)

    # Step 2: Sort by overall_score in descending order
    ranked_results = sorted(flat_results, key=lambda x: x["overall_score"], reverse=True)

    # Step 3: Display the results in ranked order
    print("🎯 Ranked Resume Results:\n")
    for i, res in enumerate(ranked_results, start=1):
        print(f"{i}. {res['resume_filename']} - Score: {res['overall_score']} - Tag: {res['tag']}")


crew = Crew(
        agents=[summarizer, evaluation_agent, interview_agent, editor_agent, output_parser_agent],
        tasks=[summarization_task, evaluation_task, interview_task, editor_task, output_parser_task],
        verbose=False
    )



# def main():
#     parser = argparse.ArgumentParser(description='Batch process resumes against a job description.')
#     parser.add_argument('--resumes_folder', type=str, required=True, help='Path to the folder containing resumes')
#     parser.add_argument('--job_description', type=str, required=True, help='Path to the job description file')
#     args = parser.parse_args()

#     job_description_text = extract_text(args.job_description)
#     all_results = []

#     crew = Crew(
#         agents=[summarizer, evaluation_agent, interview_agent, editor_agent, output_parser_agent],
#         tasks=[summarization_task, evaluation_task, interview_task, editor_task, output_parser_task],
#         verbose=False
#     )

#     # Ensure the output file is empty at the beginning of the run
#     output_file_path = "D:\\HR_AGENTIC_SOLUTION\\output.txt"
#     with open(output_file_path, "w", encoding="utf-8") as f:
#         pass  # This clears the file

#     for resume_filename in os.listdir(args.resumes_folder):
#         resume_path = os.path.join(args.resumes_folder, resume_filename)
#         if not resume_filename.lower().endswith(('.pdf', '.docx', '.txt')):
#             print(f"Skipping unsupported file format: {resume_filename}")
#             continue

#         print(f"\nProcessing resume: {resume_filename}")
#         try:
#             resume_text = extract_text(resume_path)

#             result = crew.kickoff(inputs={
#                 "resume": resume_text,
#                 "job_description": job_description_text
#             })

#             parsed_output = clean_output(output_parser_task.output.raw)

#             # # ⬇️ Store into all_results
#             try:
#                 all_results.append(json.loads(parsed_output))
#             except json.JSONDecodeError as e:
#                 print(f"⚠️ Failed to parse JSON for {resume_filename}: {e}")
#                 continue

#         except Exception as e:
#             print(f"Error processing {resume_filename}: {e}")

#     # Print the full list
#     print(json.dumps(all_results, indent=2))

#     # Generate a dynamic filename using the current date and time
#     timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
#     filename = f"output_{timestamp}.txt"

#     # Create and write to the file
#     with open(filename, "w", encoding="utf-8") as file:
#         file.write(json.dumps(all_results, indent=2))

#     # Load results and ranks
#     load_results_and_ranks(all_results)
            

# if __name__ == '__main__':
#     main()