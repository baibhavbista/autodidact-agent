"""
Tutor Session page
Interactive learning sessions with AI tutor
"""

import streamlit as st
from backend.db import (
    get_node_with_objectives,
    get_session_info
)
from backend.graph_v04 import create_session_graph


def run_tutor_response(session_info, node_info):
    """Run the v0.4 tutor graph to generate response - pure state transformation, no UI"""
    from backend.session_state import create_initial_state
    
    # Create the graph
    tutor_graph = create_session_graph()
    
    # Initialize or update state
    if 'graph_state' not in st.session_state:
        # Create initial state for the graph
        state = create_initial_state(
            session_id=session_info['id'],
            project_id=session_info['project_id'],
            node_id=session_info['node_id']
        )
        st.session_state.graph_state = state
    else:
        state = st.session_state.graph_state
    
    # Sync messages from UI state to graph state
    state['messages'] = st.session_state.messages.copy()
    
    # Track message count before invocation
    prev_msg_count = len(state['messages'])
    
    try:
        # Run the graph with recursion limit
        # FIXME: should recursion limit be this high?
        config = {"recursion_limit": 50}
        for event in tutor_graph.stream(state, config):
            # Update state with latest event
            for node_name, node_state in event.items():
                state = node_state
                st.session_state.graph_state = state
        
        # Sync messages back from graph state to UI state
        st.session_state.messages = state['messages'].copy()
        st.session_state.turn_count = state.get('turn_count', 0)
        st.session_state.current_phase = state.get('current_phase', 'teaching')
        
        # Return info about what happened
        return {
            'success': True,
            'new_message_count': len(state['messages']) - prev_msg_count,
            'is_completed': state.get('current_phase') == 'completed',
            'final_score': sum(state.get('objective_scores', {}).values()) / len(state['objective_scores']) if state.get('objective_scores') else 0
        }
        
    except Exception as e:
        # Return error info without displaying UI
        error_type = 'unknown'
        if "AuthenticationError" in str(type(e)):
            error_type = 'auth'
        elif "RateLimitError" in str(type(e)):
            error_type = 'rate_limit'
        elif "GraphRecursionError" in str(type(e)):
            error_type = 'recursion'
        
        return {
            'success': False,
            'error': str(e),
            'error_type': error_type,
            'debug_info': {
                "session_id": session_info['id'],
                "current_phase": state.get('current_phase', 'unknown'),
                "message_count": len(st.session_state.messages),
                "objectives_to_teach": len(state.get('objectives_to_teach', [])),
                "completed_objectives": len(state.get('completed_objectives', set()))
            }
        }


# Get session info from URL or session state
project_id = st.query_params.get("project_id")
session_id = st.query_params.get("session_id")

# If not in URL but we have them in session state, set them in URL
if not project_id and "selected_project_id" in st.session_state:
    project_id = st.session_state.selected_project_id
    st.query_params["project_id"] = project_id
    del st.session_state.selected_project_id

if not session_id and "selected_session_id" in st.session_state:
    session_id = st.session_state.selected_session_id
    st.query_params["session_id"] = session_id
    del st.session_state.selected_session_id

if not project_id or not session_id:
    st.error("Invalid session URL!")
    if st.button("Go to Projects"):
        st.switch_page("pages/home.py")
    st.stop()

# Get session information
session_info = get_session_info(session_id)
print(f"session_info: {session_info}")
if not session_info:
    st.error("Session not found!")
    if st.button("Go to Project"):
        if project_id:
            st.session_state.selected_project_id = project_id
            st.switch_page("pages/project_detail.py")
        else:
            st.switch_page("pages/home.py")
    st.stop()

# # Initialize session state for this session
# if "messages" not in st.session_state:
#     st.session_state.messages = []
# # Remove the graph_state initialization - let run_tutor_response handle it

# Get node information
node_info = get_node_with_objectives(session_info['node_id'])
if not node_info:
    st.error("Node information not found!")
    st.stop()

# # Check if this is a completed session
is_completed = session_info["status"] == "completed"

# Header
if is_completed:
    st.info(f"📚 **Completed Session** - Score: {int(session_info['final_score'] * 100)}%")
st.markdown(f"## 🎓 Learning Session: {node_info['label']}")

@st.dialog("Session Info", width="large")
def session_info_dialog():
    st.info(f"**Topic:** {node_info['label']}")
    st.markdown("### 📋 Learning Objectives")
    for i, obj in enumerate(node_info['learning_objectives'], 1):
        st.markdown(f"{i}. {obj['description']}")
    st.markdown("### 📚 References")
    # node_references_sections and stuff like that should be in node_info but was easier to add in session_info, need to fix TODO
    for i, ref in enumerate(session_info['node_references_sections'], 1):
        nat_lang_section_text = ref.get("section") or ref.get("loc") or ""
        if nat_lang_section_text:
            nat_lang_section_text = f"({nat_lang_section_text})"
        st.markdown(f"{i}. [{ref['title']}]({ref['url']}) {nat_lang_section_text}")

# Session control buttons
with st.container():
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚪 Exit Session", type="secondary", use_container_width=True):
            st.session_state.selected_project_id = project_id
            st.switch_page("pages/project_detail.py")

    with col2:
        if not is_completed and st.session_state.get('graph_state'):
            # Only show early end if session is active and we've started teaching
            if st.session_state.graph_state.get('current_phase') in ['teaching', 'final_test']:
                if st.button("⏹️ End Session Early", type="secondary", use_container_width=True):
                    # Set the force end flag and run the graph
                    st.session_state.graph_state['force_end_session'] = True
                    st.session_state.messages.append({
                        "role": "user",
                        "content": "I'd like to end the session early please."
                    })
                    st.rerun()

    with col3:
        # add session info button here which opens a modal with the session info
        if st.button("📚 Session Info", type="secondary", use_container_width=True):
            session_info_dialog()

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle initial message generation
if not is_completed and len(st.session_state.messages) == 0:
    # Generate initial welcome message
    with st.chat_message("assistant"):
        with st.spinner("🤔 Preparing session..."):
            result = run_tutor_response(session_info, node_info)
            if result['success']:
                # Display the new message(s)
                new_messages = st.session_state.messages[-result['new_message_count']:]
                for msg in new_messages:
                    if msg["role"] == "assistant":
                        st.markdown(msg["content"])
            else:
                st.error(f"❌ Failed to start session: {result['error']}")

# Accept user input (disabled for completed sessions)
if not is_completed:
    if prompt := st.chat_input("Your response..."):
        
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Display assistant response in chat message container
        with st.chat_message("assistant"):
            with st.spinner("🤔 Thinking..."):
                result = run_tutor_response(session_info, node_info)
                
                if result['success']:
                    # Display new assistant messages
                    new_messages = st.session_state.messages[-result['new_message_count']:]
                    for msg in new_messages:
                        if msg["role"] == "assistant":
                            st.markdown(msg["content"])
                    
                    print(f"result: {result}")
                    print(f"st.session_state.messages: {st.session_state.messages}")
                    
                    # Check if session is completed
                    if result['is_completed']:
                        st.balloons()
                        st.success(f"🎉 **Session Complete!** Your score: {int(result['final_score'] * 100)}%")
                        
                        # Show completion buttons
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("✅ Back to Project", type="primary", use_container_width=True):
                                st.session_state.selected_project_id = session_info['project_id']
                                st.switch_page("pages/project_detail.py")
                        
                        with col2:
                            if st.button("📊 View Progress", type="secondary", use_container_width=True):
                                st.session_state.selected_project_id = session_info['project_id']
                                st.switch_page("pages/project_detail.py")
                else:
                    # Handle errors
                    if result['error_type'] == 'auth':
                        st.error("❌ API key authentication failed. Please check your API key in Settings.")
                        if st.button("Go to Settings"):
                            st.switch_page("pages/settings.py")
                    elif result['error_type'] == 'rate_limit':
                        st.error("⏳ Rate limit reached. Please wait a moment and try again.")
                        st.info("Consider upgrading your OpenAI plan for higher rate limits.")
                    elif result['error_type'] == 'recursion':
                        st.error("⚠️ Session is taking too long. The conversation might be stuck in a loop.")
                        st.info("Try refreshing the page or starting a new session.")
                    else:
                        st.error(f"❌ Error in tutor response: {result['error']}")
                        st.info("Try refreshing the page or starting a new session.")
                    
                    # Show debug info in expander
                    with st.expander("🐛 Debug Information"):
                        st.json(result['debug_info'])
else:
    st.info("This session has been completed. Exit to start a new session on a different topic!")