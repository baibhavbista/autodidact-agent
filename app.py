"""
Autodidact - AI-Powered Learning Assistant
Main Streamlit application
"""

import streamlit as st
import uuid
import json
from pathlib import Path
from typing import Optional, List

# Import our modules
from backend.db import (
    init_database, 
    get_project, 
    create_project,
    save_graph_to_db,
    get_next_nodes
)
from backend.jobs import (
    clarify_topic,
    is_skip_response,
    process_clarification_responses,
    run_deep_research_job
)
from utils.config import (
    load_api_key, 
    save_api_key, 
    CONFIG_FILE,
    save_project_files
)
from components.graph_viz import (
    create_knowledge_graph,
    format_report_with_footnotes
)


# Page configuration
st.set_page_config(
    page_title="Autodidact - AI Learning Assistant",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database
init_database()


def init_session_state():
    """Initialize Streamlit session state variables"""
    if "project_id" not in st.session_state:
        st.session_state.project_id = None
    if "current_node" not in st.session_state:
        st.session_state.current_node = None
    if "in_session" not in st.session_state:
        st.session_state.in_session = False
    if "api_key" not in st.session_state:
        st.session_state.api_key = load_api_key()
    if "clarification_state" not in st.session_state:
        st.session_state.clarification_state = None
    if "clarification_attempts" not in st.session_state:
        st.session_state.clarification_attempts = 0


def show_api_key_modal():
    """Show modal for API key setup"""
    with st.container():
        st.markdown("### 🔑 API Key Setup")
        st.info(
            "Autodidact requires an OpenAI API key to function. "
            "Your key will be stored locally and securely on your machine."
        )
        
        api_key = st.text_input(
            "Enter your OpenAI API key:",
            type="password",
            help="Your API key will be stored in ~/.autodidact/.env.json with secure permissions"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save API Key", type="primary"):
                if api_key and api_key.startswith("sk-"):
                    save_api_key(api_key)
                    st.session_state.api_key = api_key
                    st.success("API key saved successfully!")
                    st.rerun()
                else:
                    st.error("Please enter a valid OpenAI API key (should start with 'sk-')")
        
        with col2:
            st.link_button(
                "Get API Key",
                "https://platform.openai.com/api-keys",
                help="Click to open OpenAI's API key page"
            )


def handle_clarification(topic: str, hours: int):
    """Handle the clarification flow"""
    # Check if we need clarification
    if st.session_state.clarification_state is None:
        with st.spinner("Analyzing your topic..."):
            try:
                result = clarify_topic(topic, hours)
                st.session_state.clarification_state = result
                st.session_state.clarification_attempts = 0
            except Exception as e:
                st.error(f"Error during topic analysis: {str(e)}")
                return
    
    result = st.session_state.clarification_state
    
    if result["need_clarification"]:
        st.markdown("### 🤔 Let me understand better...")
        st.info("Your topic is quite broad. Please help me narrow it down by answering a few questions:")
        
        # Show questions and collect responses
        responses = []
        for i, question in enumerate(result["questions"]):
            response = st.text_input(
                f"{i+1}. {question}",
                key=f"clarification_q_{i}",
                help="Type 'skip' or 'idk' if you're not sure"
            )
            responses.append(response)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Submit Answers", type="primary"):
                # Check for skip responses
                skip_count = sum(1 for r in responses if is_skip_response(r))
                
                if skip_count == len(responses) and st.session_state.clarification_attempts < 2:
                    st.warning("⚠️ Please try to answer at least one question to help me create a better learning plan.")
                    st.session_state.clarification_attempts += 1
                else:
                    # Process responses
                    refined_topic = process_clarification_responses(result["questions"], responses)
                    if refined_topic:
                        topic = refined_topic
                    
                    # Start Deep Research
                    start_deep_research(topic, hours)
        
        with col2:
            if st.button("Skip Clarification"):
                # Use original topic
                start_deep_research(topic, hours)
    else:
        # No clarification needed, start Deep Research
        refined_topic = result.get("refined_topic", topic)
        start_deep_research(refined_topic, hours)


def start_deep_research(topic: str, hours: int):
    """Start the Deep Research process"""
    st.session_state.clarification_state = None  # Reset clarification
    
    with st.spinner(f"🔍 Conducting deep research on: {topic}\n\nThis may take 10-30 minutes..."):
        try:
            # Run Deep Research
            result = run_deep_research_job(topic, hours)
            
            # Create a temporary project ID for file storage
            temp_project_id = str(uuid.uuid4())
            
            # Save files to disk
            report_path = save_project_files(
                temp_project_id,
                result["report_markdown"],
                result["graph"],
                result
            )
            
            # Create project record (this creates the actual project_id)
            project_id = create_project(
                topic=topic,
                report_path=report_path,
                graph_json=result["graph"],
                footnotes=result["footnotes"]
            )
            
            # Save graph to database
            save_graph_to_db(project_id, result["graph"])
            
            # Update session state
            st.session_state.project_id = project_id
            
            st.success("✅ Research complete! Your personalized learning plan is ready.")
            st.rerun()
            
        except Exception as e:
            st.error(f"Error during Deep Research: {str(e)}")
            st.info("Please try again with a different topic or check your API key.")


def show_welcome_screen():
    """Show the welcome/landing screen"""
    st.markdown("# 🧠 Autodidact")
    st.markdown("### Your AI-Powered Learning Assistant")
    
    st.markdown("""
    Welcome to Autodidact! I'm here to help you learn any topic through:
    - 🔍 **Deep Research**: I'll investigate your topic and create a comprehensive study plan
    - 📊 **Knowledge Graphs**: Visual representation of concepts and their prerequisites  
    - 👨‍🏫 **AI Tutoring**: Personalized 30-minute learning sessions
    - 📈 **Progress Tracking**: Monitor your mastery of each concept
    """)
    
    st.markdown("---")
    
    # Topic input section
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### What would you like to learn?")
        
        topic = st.text_input(
            "Enter a topic:",
            placeholder="e.g., Foundations of Statistical Learning, Bitcoin consensus mechanisms",
            label_visibility="collapsed"
        )
        
        hours = st.number_input(
            "Target study hours (optional):",
            min_value=1,
            max_value=100,
            value=8,
            help="This helps me plan the depth of coverage"
        )
        
        if st.button("Start Learning Journey", type="primary", use_container_width=True):
            if topic:
                # Handle clarification flow
                handle_clarification(topic, hours)
            else:
                st.error("Please enter a topic to learn")
    
    # Example topics
    with st.expander("📚 Example Topics"):
        st.markdown("""
        - Foundations of Statistical Learning
        - React Hooks and State Management
        - Bitcoin and Ethereum Internals
        - Quantum Computing Basics
        - Modern World History: 1900-1950
        - Introduction to Neuroscience
        """)


def show_workspace():
    """Show the main workspace with report and graph"""
    project = get_project(st.session_state.project_id)
    if not project:
        st.error("Project not found!")
        if st.button("Go Back"):
            st.session_state.project_id = None
            st.rerun()
        return
    
    st.markdown(f"# 📚 {project['topic']}")
    
    # Two-column layout
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Report viewer
        with st.expander("📄 Research Report", expanded=False):
            try:
                # Load report and footnotes
                report_path = Path(project['report_path'])
                if report_path.exists():
                    report_md = report_path.read_text(encoding='utf-8')
                    footnotes = json.loads(project['footnotes_json'])
                    
                    # Format with footnotes
                    formatted_report = format_report_with_footnotes(report_md, footnotes)
                    st.markdown(formatted_report, unsafe_allow_html=True)
                else:
                    st.warning("Report file not found")
            except Exception as e:
                st.error(f"Error loading report: {str(e)}")
        
        st.markdown("---")
        
        # Session controls
        st.markdown("### 🎓 Learning Sessions")
        
        # Get available nodes
        next_nodes = get_next_nodes(st.session_state.project_id)
        
        if next_nodes:
            if len(next_nodes) == 1:
                st.info(f"Ready to learn: **{next_nodes[0]['label']}**")
                if st.button("Start Session", type="primary", use_container_width=True):
                    st.session_state.current_node = next_nodes[0]['id']
                    st.session_state.in_session = True
                    st.rerun()
            else:
                # Multiple options
                st.info("Choose your next topic:")
                selected = st.radio(
                    "Available topics:",
                    options=[n['id'] for n in next_nodes],
                    format_func=lambda x: next(n['label'] for n in next_nodes if n['id'] == x),
                    label_visibility="collapsed"
                )
                if st.button("Start Session", type="primary", use_container_width=True):
                    st.session_state.current_node = selected
                    st.session_state.in_session = True
                    st.rerun()
        else:
            st.success("🎉 Congratulations! You've completed all available topics!")
    
    with col2:
        # Knowledge graph visualization
        st.markdown("### 📊 Knowledge Graph")
        
        try:
            # Load graph data
            graph_data = json.loads(project['graph_json'])
            
            # Get node mastery data
            # TODO: Query actual mastery from database
            node_mastery = {node['id']: 0.0 for node in graph_data['nodes']}
            
            # Create graph
            graph_viz = create_knowledge_graph(
                graph_data['nodes'],
                graph_data['edges'],
                node_mastery
            )
            
            # Display graph
            st.graphviz_chart(graph_viz.source)
            
        except Exception as e:
            st.error(f"Error displaying graph: {str(e)}")


def show_tutor_session():
    """Show the tutor session interface"""
    # TODO: Implement tutor session
    st.markdown("## 🎓 Tutor Session")
    
    if st.button("End Session (temporary)"):
        st.session_state.in_session = False
        st.rerun()
    
    st.info("Tutor session implementation coming in Phase 4")


def main():
    """Main application entry point"""
    # Initialize session state
    init_session_state()
    
    # Sidebar
    with st.sidebar:
        st.markdown("# 🧠 Autodidact")
        
        if st.session_state.api_key:
            st.success("✅ API Key configured")
            
            if st.button("⚙️ Settings"):
                if st.button("Clear API Key"):
                    CONFIG_FILE.unlink(missing_ok=True)
                    st.session_state.api_key = None
                    st.rerun()
        else:
            st.warning("⚠️ API Key not configured")
        
        st.markdown("---")
        
        # Project selection (if any exist)
        if st.session_state.project_id:
            project = get_project(st.session_state.project_id)
            if project:
                st.markdown(f"**Current Project:**")
                st.markdown(f"📚 {project['topic']}")
                
                if st.button("🏠 New Project"):
                    st.session_state.project_id = None
                    st.session_state.current_node = None
                    st.session_state.in_session = False
                    st.session_state.clarification_state = None
                    st.rerun()
    
    # Main content area
    if not st.session_state.api_key:
        show_api_key_modal()
    elif not st.session_state.project_id:
        show_welcome_screen()
    elif st.session_state.in_session:
        show_tutor_session()
    else:
        show_workspace()
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: gray;'>"
        "Built with ❤️ for autodidacts everywhere | "
        "<a href='https://github.com/yourusername/autodidact'>GitHub</a>"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main() 