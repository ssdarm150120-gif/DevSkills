# shellcheck shell=bash

Describe 'hook vetar_acciones_externas.sh'
  # Evento PreToolUse de Bash. $1 = comando; $2 = "subagente" o "principal".
  evento() {
    if [[ "$2" == "subagente" ]]; then
      printf '{"session_id":"s1","agent_id":"agent-7","agent_type":"devskills:dev-a","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"%s"}}' "$1"
    else
      printf '{"session_id":"s1","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"%s"}}' "$1"
    fi
  }
  hook() {
    evento "$1" "$2" | bash "$PROJECT_ROOT/hooks/vetar_acciones_externas.sh"
  }

  Describe 'bloquea a los subagentes'
    Parameters
      'git push origin main'
      'git -C /ruta/repo push --force'
      'cd x && git push'
      'git branch -D hu-12'
      'git branch --delete --force hu-12'
      'gh issue create --title x'
      'gh pr merge 5 --squash'
      'gh repo create org/x --private'
      'gh release create v1'
      'gh run rerun 123'
      'gh api repos/o/r/issues -f title=x'
      'gh api -X DELETE repos/o/r'
      'gh auth token'
      'docker push ghcr.io/o/x:1'
      'docker login ghcr.io'
      'docker system prune -af'
      'docker volume prune -f'
    End
    It "veta: $1"
      When call hook "$1" subagente
      The status should eq 2
      The stderr should include 'bloqueado para subagentes'
    End
  End

  Describe 'deja pasar lo legítimo de un subagente'
    Parameters
      'git status --short'
      'git diff --stat'
      'git restore codigo/app.py'
      'git branch -d hu-12'
      'git log --oneline -5'
      'gh run list --limit 3'
      'gh run view 123 --log-failed'
      'gh api repos/o/r/actions/runs'
      'docker compose -p miapp-dev-a up -d'
      'python -m pytest -q'
    End
    It "permite: $1"
      When call hook "$1" subagente
      The status should be success
    End
  End

  Describe 'no toca al hilo principal (el orquestador)'
    It 'permite git push sin agent_id: la confirmación del usuario la piden las skills'
      When call hook 'git push origin main' principal
      The status should be success
    End
  End

  Describe 'entrada rara'
    It 'sin comando no hace nada'
      Data '{"agent_id":"a1","tool_name":"Bash","tool_input":{}}'
      When run bash "$PROJECT_ROOT/hooks/vetar_acciones_externas.sh"
      The status should be success
    End
  End
End
