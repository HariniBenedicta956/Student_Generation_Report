AI-Powered Student Assessment Report Generation – Project Statement
 
Project Overview
 
This project aims to automate the generation of personalized student assessment reports using Large Language Models (LLMs), enabling scalable, consistent, and cost-effective report creation for educational institutions and assessment platforms.
 
Each report combines structured assessment data with AI-generated narratives to produce a professional PDF containing:
 
•	Individual performance summary
 
•	Strengths and improvement areas
 
•	Learning recommendations
 
•	Career and skill development guidance
 
•	Overall assessment insights
 
The objective is to minimize manual effort while maintaining high-quality, personalized feedback for every student.
 
Estimated AI Token Consumption
 
Based on three sample reports generated during development:
 
Report	Words	Characters	Estimated Output Tokens
 
Nishaleni	511	3,769	~940
 
Maha Lakshmi	517	3,810	~950
 
Mohammed Nizamudeen	529	3,920	~980
 
Total	1,557	11,499	~2,870
 
Assuming a compact prompt and structured student profile consume approximately 1,700–1,900 input tokens, the estimated usage is:
 
•	Per student: ~2,650–2,900 total tokens
 
•	Three reports: ~8,000–8,700 total tokens
 
These estimates exclude internal model reasoning tokens and may be reduced through prompt caching and deterministic template generation.
 
Estimated API Cost
 
Using an estimated workload of:
 
•	Input: ~1,800 tokens
 
•	Output: ~960 tokens
 
Approximate cost per student report:
 
Model	Standard Cost	Batch Cost	Approx. INR
 
GPT-5.6 Luna	$0.0076	$0.0038	₹0.65 / ₹0.33
 
GPT-5.6 Terra	$0.0189	$0.0095	₹1.63 / ₹0.81
 
GPT-5.6 Sol	$0.0378	$0.0189	₹3.25 / ₹1.63
 
For the three sample reports:
 
•	GPT-5.6 Luna: approximately $0.023 (around ₹2)
 
Estimated production cost for 300 student reports:
 
•	Luna Standard: approximately ₹195
 
•	Luna Batch API: approximately ₹97
 
These estimates cover only model inference costs and exclude infrastructure, storage, document generation, maintenance, and development expenses.
 
Recommended Production Architecture
 
For large-scale deployment, the recommended workflow is:
 
 
1. 
 

 
Calculate assessment scores, classifications, and performance metrics within the master spreadsheet or backend system.
 
 
1. 
 

 
Generate a compact student profile containing only the essential structured information.
 
 
1. 
 

 
Submit the profile to GPT-5.6 Luna (Batch API) to generate the narrative in structured JSON format.
 
 
1. 
 

 
Produce the final PDF using deterministic templates (Python or document-generation libraries), ensuring consistent branding and formatting.
 
This architecture offers:
 
•	High scalability
 
•	Consistent report formatting
 
•	Reduced AI token consumption
 
•	Faster processing
 
•	Lower operational costs
 
Expected Production Cost
 
By leveraging prompt caching, compact prompts, structured inputs, and deterministic PDF generation, the expected AI inference cost is:
 
Approximately ₹0.25–₹0.40 per student report.
 
This makes the solution economically viable for institutions generating hundreds or thousands of assessment reports while maintaining personalized, AI-assisted feedback quality.
 
Conclusion
 
The proposed architecture demonstrates that AI-powered student assessment reporting can be deployed at scale with minimal operational cost. By separating deterministic data processing from AI narrative generation, the system achieves an optimal balance between personalization, consistency, and cost efficiency, making it suitable for enterprise and educational deployments