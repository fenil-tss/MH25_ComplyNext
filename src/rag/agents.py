from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from typing import List

# --- Pydantic Models ---
class ComplianceAlert(BaseModel):
    applicability_status: str = Field(..., description="APPLICABLE or NOT_APPLICABLE")
    summary: str = Field(..., description="Plain English summary")
    action_items: List[str] = Field(..., description="Specific actions needed")
    risk_level: str = Field(..., description="HIGH, MEDIUM, LOW")

class AgentSystem:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4-turbo", temperature=0)

    def assess_impact(self, profile_text: str, regulatory_context: str) -> ComplianceAlert:
        """
        Compares company profile against retrieved regulatory chunks.
        """
        prompt = ChatPromptTemplate.from_template("""
        You are a Fintech Compliance Officer.
        
        COMPANY PROFILE:
        {profile}
        
        RELEVANT REGULATORY CLAUSES (Retrieved from Database):
        {context}
        
        TASK:
        1. Does this regulation apply to the company?
        2. What actions must they take?
        3. Explain in plain English.
        
        Output strict JSON.
        """)
        
        chain = prompt | self.llm.with_structured_output(ComplianceAlert)
        return chain.invoke({
            "profile": profile_text, 
            "context": regulatory_context
        })
    
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from typing import List

# --- Pydantic Models ---
class ComplianceAlert(BaseModel):
    applicability_status: str = Field(..., description="APPLICABLE or NOT_APPLICABLE")
    summary: str = Field(..., description="Plain English summary")
    action_items: List[str] = Field(..., description="Specific actions needed")
    risk_level: str = Field(..., description="HIGH, MEDIUM, LOW")
