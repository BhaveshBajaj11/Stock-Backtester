import React, { useState, useMemo } from 'react';
import { Layout } from './components/layout/Layout';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from './components/ui/Card';
import { Button } from './components/ui/Button';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { motion } from 'framer-motion';
import { Modal } from './components/ui/Modal';
import { ProjectForm } from './components/projects/ProjectForm';
import { ConfirmDialog } from './components/ui/ConfirmDialog';
import { SearchInput } from './components/ui/SearchInput';
import { Select } from './components/ui/Select';
import { useDispatch, useSelector } from 'react-redux';
import { addProject, updateProject, deleteProject } from './store/projectSlice';
import { deleteProjectTasks } from './store/taskSlice';
import { RootState } from './store';
import { TaskList } from './components/tasks/TaskList';

interface Project {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
}

type SortOption = 'name-asc' | 'name-desc' | 'updated-asc' | 'updated-desc' | 'created-asc' | 'created-desc';

function App() {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('updated-desc');
  
  const dispatch = useDispatch();
  const projects = useSelector((state: RootState) => state.projects.projects);
  const tasks = useSelector((state: RootState) => state.tasks.tasks);

  // Filter and sort projects
  const filteredAndSortedProjects = useMemo(() => {
    let result = [...projects];
    
    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        project =>
          project.name.toLowerCase().includes(query) ||
          project.description.toLowerCase().includes(query)
      );
    }
    
    // Sort projects
    result.sort((a, b) => {
      switch (sortBy) {
        case 'name-asc':
          return a.name.localeCompare(b.name);
        case 'name-desc':
          return b.name.localeCompare(a.name);
        case 'updated-asc':
          return new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime();
        case 'updated-desc':
          return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
        case 'created-asc':
          return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
        case 'created-desc':
          return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
        default:
          return 0;
      }
    });
    
    return result;
  }, [projects, searchQuery, sortBy]);

  const getProjectStats = (projectId: string) => {
    const projectTasks = tasks.filter(task => task.projectId === projectId);
    const completedTasks = projectTasks.filter(task => task.status === 'completed');
    const progress = projectTasks.length > 0
      ? (completedTasks.length / projectTasks.length) * 100
      : 0;

    return {
      total: projectTasks.length,
      completed: completedTasks.length,
      progress,
    };
  };

  const handleCreateProject = async (data: { name: string; description: string }) => {
    setIsSubmitting(true);
    try {
      const newProject = {
        id: Date.now().toString(),
        name: data.name,
        description: data.description,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      
      dispatch(addProject(newProject));
      setIsCreateModalOpen(false);
    } catch (error) {
      console.error('Failed to create project:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEditProject = async (data: { name: string; description: string }) => {
    if (!selectedProject) return;
    
    setIsSubmitting(true);
    try {
      const updatedProject = {
        ...selectedProject,
        name: data.name,
        description: data.description,
        updatedAt: new Date().toISOString(),
      };
      
      dispatch(updateProject(updatedProject));
      setIsEditModalOpen(false);
      setSelectedProject(null);
    } catch (error) {
      console.error('Failed to update project:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteProject = async () => {
    if (!selectedProject) return;
    
    setIsSubmitting(true);
    try {
      dispatch(deleteProject(selectedProject.id));
      dispatch(deleteProjectTasks(selectedProject.id));
      setIsDeleteDialogOpen(false);
      setSelectedProject(null);
    } catch (error) {
      console.error('Failed to delete project:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const openEditModal = (project: Project) => {
    setSelectedProject(project);
    setIsEditModalOpen(true);
  };

  const openDeleteDialog = (project: Project) => {
    setSelectedProject(project);
    setIsDeleteDialogOpen(true);
  };

  return (
    <Layout>
      <div className="space-y-8">
        {/* Header Section */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
            <p className="text-muted-foreground">Manage your projects and tasks.</p>
          </div>
          <Button size="sm" className="gap-2" onClick={() => setIsCreateModalOpen(true)}>
            <Plus className="h-4 w-4" />
            New Project
          </Button>
        </div>

        {/* Filters Section */}
        <div className="flex gap-4">
          <SearchInput
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-sm"
          />
          <Select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortOption)}
            className="w-48"
          >
            <option value="updated-desc">Latest Update</option>
            <option value="updated-asc">Oldest Update</option>
            <option value="created-desc">Latest Created</option>
            <option value="created-asc">Oldest Created</option>
            <option value="name-asc">Name (A-Z)</option>
            <option value="name-desc">Name (Z-A)</option>
          </Select>
        </div>

        {/* Projects Grid */}
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {filteredAndSortedProjects.map((project) => {
            const stats = getProjectStats(project.id);
            return (
              <Card key={project.id} variant="glass" className="group">
                <CardHeader>
                  <CardTitle>{project.name}</CardTitle>
                  <CardDescription>
                    Last updated {new Date(project.updatedAt).toLocaleDateString()}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {project.description}
                    </p>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Tasks</span>
                      <span className="text-sm font-medium">
                        {stats.completed}/{stats.total}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-secondary">
                      <motion.div
                        className="h-full rounded-full bg-primary"
                        initial={{ width: '0%' }}
                        animate={{ width: `${stats.progress}%` }}
                        transition={{ duration: 1 }}
                      />
                    </div>
                  </div>
                </CardContent>
                <CardFooter className="justify-end gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => openEditModal(project)}
                  >
                    <Pencil className="h-4 w-4" />
                    <span className="sr-only">Edit</span>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => openDeleteDialog(project)}
                  >
                    <Trash2 className="h-4 w-4" />
                    <span className="sr-only">Delete</span>
                  </Button>
                </CardFooter>
              </Card>
            );
          })}
        </div>

        {filteredAndSortedProjects.length === 0 && (
          <div className="text-center py-12">
            <p className="text-muted-foreground">No projects found.</p>
          </div>
        )}

        {/* Selected Project Tasks */}
        {selectedProject && (
          <TaskList projectId={selectedProject.id} />
        )}
      </div>

      {/* Create Project Modal */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="Create New Project"
      >
        <ProjectForm
          onSubmit={handleCreateProject}
          onCancel={() => setIsCreateModalOpen(false)}
          isSubmitting={isSubmitting}
        />
      </Modal>

      {/* Edit Project Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => {
          setIsEditModalOpen(false);
          setSelectedProject(null);
        }}
        title="Edit Project"
      >
        <ProjectForm
          initialData={selectedProject || undefined}
          onSubmit={handleEditProject}
          onCancel={() => {
            setIsEditModalOpen(false);
            setSelectedProject(null);
          }}
          isSubmitting={isSubmitting}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={isDeleteDialogOpen}
        onClose={() => {
          setIsDeleteDialogOpen(false);
          setSelectedProject(null);
        }}
        onConfirm={handleDeleteProject}
        title="Delete Project"
        description="Are you sure you want to delete this project? This action cannot be undone."
        confirmText="Delete"
        variant="destructive"
        isSubmitting={isSubmitting}
      />
    </Layout>
  );
}

export default App; 