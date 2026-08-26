from pydantic import BaseModel, Field
from typing import List, Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class Email(BaseModel):
    id: str = Field(default="1", description="Unique identifier of the email")
    threadId: str = Field(default="1", description="Thread identifier of the email")
    messageId: str = Field(default="1", description="Message identifier of the email")
    references: str = Field(default="1", description="References of the email")
    sender: str = Field(default="client@example.com", description="Email address of the sender")
    subject: str = Field(default="Inquiry regarding service plans and pricing", description="Subject line of the email")
    body: str = Field(default="Hi, I would like to know more about your agency service plans and pricing.", description="Body content of the email")
    
class GraphState(TypedDict):
    emails: List[Email]
    current_email: Email
    email_category: str
    generated_email: str
    rag_queries: List[str]
    retrieved_documents: str
    writer_messages: Annotated[list, add_messages]
    sendable: bool
    trials: int